"""Cross-source deduplication for arXiv items.

This module provides deduplication logic for arXiv items collected from
multiple sources (RSS feeds and API queries).
"""

from dataclasses import dataclass, field
from typing import Protocol

import structlog

from src.collectors.arxiv.constants import (
    FIELD_MERGED_FROM_SOURCES,
    FIELD_SOURCE,
    FIELD_SOURCE_IDS,
    FIELD_TIMESTAMP_NOTE,
    MIN_TIMESTAMPS_FOR_COMPARISON,
    SOURCE_TYPE_API,
    TIMESTAMP_DIFF_THRESHOLD_SECONDS,
    TIMESTAMP_NOTE_API_PREFERRED,
)
from src.collectors.arxiv.utils import extract_arxiv_id
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()


class MetricsRecorder(Protocol):
    """Protocol for metrics recording.

    Allows dependency injection of metrics for testing.
    """

    def record_deduped(self, count: int) -> None:
        """Record deduplicated item count."""
        ...


@dataclass
class DeduplicationResult:
    """Result of deduplication operation.

    Attributes:
        items: Deduplicated items.
        original_count: Number of items before deduplication.
        deduped_count: Number of items removed as duplicates.
        merged_ids: arXiv IDs that were merged.
    """

    items: list[Item]
    original_count: int
    deduped_count: int
    merged_ids: list[str] = field(default_factory=list)

    @property
    def final_count(self) -> int:
        """Get final item count after deduplication."""
        return len(self.items)


@dataclass
class ItemCandidate:
    """Candidate item for deduplication.

    Tracks an item and its source for merge decision making.
    """

    item: Item
    arxiv_id: str
    is_api_source: bool
    has_published_at: bool
    date_confidence: DateConfidence


class ArxivDeduplicator:
    """Deduplicator for arXiv items across multiple sources.

    Uses arXiv ID as the primary key for deduplication. When the same
    arXiv ID appears in multiple sources:
    - Prefers API source timestamps (considered more authoritative)
    - Marks merged items with date_confidence=medium if timestamps differ
    - Keeps the item with the most complete metadata
    """

    def __init__(
        self,
        run_id: str = "",
        metrics: MetricsRecorder | None = None,
    ) -> None:
        """Initialize the deduplicator.

        Args:
            run_id: Run identifier for logging.
            metrics: Optional metrics recorder for dependency injection.
                     Defaults to ArxivMetrics singleton.
        """
        # Import here to avoid circular import and allow DI
        from src.collectors.arxiv.metrics import ArxivMetrics

        self._run_id = run_id
        self._metrics: MetricsRecorder = metrics or ArxivMetrics.get_instance()
        self._log = logger.bind(
            component="arxiv",
            run_id=run_id,
            operation="dedupe",
        )

    def deduplicate(self, items: list[Item]) -> DeduplicationResult:
        """Deduplicate items by arXiv ID.

        Args:
            items: List of items to deduplicate.

        Returns:
            DeduplicationResult with deduplicated items and stats.
        """
        original_count = len(items)

        if not items:
            return DeduplicationResult(
                items=[],
                original_count=0,
                deduped_count=0,
            )

        # Group items by arXiv ID
        items_by_id: dict[str, list[ItemCandidate]] = {}

        for item in items:
            arxiv_id = extract_arxiv_id(item.url)
            if not arxiv_id:
                # Non-arXiv items pass through unchanged
                if "" not in items_by_id:
                    items_by_id[""] = []
                items_by_id[""].append(
                    ItemCandidate(
                        item=item,
                        arxiv_id="",
                        is_api_source=False,
                        has_published_at=item.published_at is not None,
                        date_confidence=item.date_confidence,
                    )
                )
                continue

            if arxiv_id not in items_by_id:
                items_by_id[arxiv_id] = []

            is_api = self._is_api_source(item)
            items_by_id[arxiv_id].append(
                ItemCandidate(
                    item=item,
                    arxiv_id=arxiv_id,
                    is_api_source=is_api,
                    has_published_at=item.published_at is not None,
                    date_confidence=item.date_confidence,
                )
            )

        # Merge items for each arXiv ID
        deduplicated: list[Item] = []
        merged_ids: list[str] = []

        for arxiv_id, candidates in items_by_id.items():
            if not arxiv_id:
                # Pass through non-arXiv items
                deduplicated.extend(c.item for c in candidates)
                continue

            if len(candidates) == 1:
                # No deduplication needed
                deduplicated.append(candidates[0].item)
            else:
                # Merge multiple items
                merged_item = self._merge_candidates(candidates)
                deduplicated.append(merged_item)
                merged_ids.append(arxiv_id)

        deduped_count = original_count - len(deduplicated)

        self._metrics.record_deduped(deduped_count)

        self._log.info(
            "deduplication_complete",
            original_count=original_count,
            final_count=len(deduplicated),
            deduped_count=deduped_count,
            merged_ids_count=len(merged_ids),
        )

        return DeduplicationResult(
            items=deduplicated,
            original_count=original_count,
            deduped_count=deduped_count,
            merged_ids=merged_ids,
        )

    def _is_api_source(self, item: Item) -> bool:
        """Check if item came from API source.

        Args:
            item: Item to check.

        Returns:
            True if item is from API source.
        """
        try:
            import json

            raw = json.loads(item.raw_json)
            return bool(raw.get(FIELD_SOURCE) == SOURCE_TYPE_API)
        except (json.JSONDecodeError, KeyError):
            return False

    def _merge_candidates(self, candidates: list[ItemCandidate]) -> Item:
        """Merge multiple candidates into a single item.

        Preference order:
        1. API source with published_at
        2. API source without published_at
        3. RSS source with published_at (highest confidence)
        4. RSS source without published_at

        Args:
            candidates: List of candidates for the same arXiv ID.

        Returns:
            Merged item.
        """
        # Sort by preference
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                # Prefer API sources (True sorts after False, so negate)
                not c.is_api_source,
                # Prefer items with published_at
                not c.has_published_at,
                # Prefer higher date confidence
                c.date_confidence != DateConfidence.HIGH,
                c.date_confidence != DateConfidence.MEDIUM,
            ),
        )

        best = sorted_candidates[0]

        # Check if timestamps differ between sources
        timestamps_differ = self._check_timestamps_differ(candidates)

        if len(candidates) > 1:
            # Always create merged item when multiple candidates exist
            return self._create_merged_item(
                best.item, candidates, timestamps_differ=timestamps_differ
            )

        return best.item

    def _check_timestamps_differ(self, candidates: list[ItemCandidate]) -> bool:
        """Check if timestamps differ between candidates.

        Args:
            candidates: List of candidates.

        Returns:
            True if timestamps differ significantly.
        """
        timestamps = [c.item.published_at for c in candidates if c.item.published_at]

        if len(timestamps) < MIN_TIMESTAMPS_FOR_COMPARISON:
            return False

        # Check if any timestamps differ by more than threshold
        for i, t1 in enumerate(timestamps):
            for t2 in timestamps[i + 1 :]:
                delta = abs((t1 - t2).total_seconds())
                if delta > TIMESTAMP_DIFF_THRESHOLD_SECONDS:
                    return True

        return False

    def _create_merged_item(
        self,
        base_item: Item,
        candidates: list[ItemCandidate],
        timestamps_differ: bool,
    ) -> Item:
        """Create a merged item from multiple candidates.

        Args:
            base_item: Base item to use for most fields.
            candidates: All candidates for this arXiv ID.
            timestamps_differ: Whether timestamps differ between sources.

        Returns:
            Merged item.
        """
        import json

        # Merge raw_json with note
        try:
            raw = json.loads(base_item.raw_json)
        except json.JSONDecodeError:
            raw = {}

        raw[FIELD_MERGED_FROM_SOURCES] = len(candidates)
        raw[FIELD_SOURCE_IDS] = [c.item.source_id for c in candidates]

        if timestamps_differ:
            raw[FIELD_TIMESTAMP_NOTE] = TIMESTAMP_NOTE_API_PREFERRED

        new_raw_json = json.dumps(raw, sort_keys=True, ensure_ascii=False)

        # Set confidence to medium if timestamps differ
        new_confidence = (
            DateConfidence.MEDIUM if timestamps_differ else base_item.date_confidence
        )

        return Item(
            url=base_item.url,
            source_id=base_item.source_id,
            tier=base_item.tier,
            kind=base_item.kind,
            title=base_item.title,
            published_at=base_item.published_at,
            date_confidence=new_confidence,
            content_hash=base_item.content_hash,
            raw_json=new_raw_json,
            first_seen_at=base_item.first_seen_at,
            last_seen_at=base_item.last_seen_at,
        )
