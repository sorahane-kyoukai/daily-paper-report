"""arXiv RSS feed collector.

This module provides a collector for arXiv RSS/Atom feeds for category subscriptions.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import mktime
from typing import Any

import feedparser  # type: ignore[import-untyped]
import structlog

from src.collectors.arxiv.metrics import ArxivMetrics
from src.collectors.arxiv.utils import (
    extract_arxiv_id,
    get_arxiv_category_from_url,
)
from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import CollectorErrorClass, ErrorRecord
from src.collectors.state_machine import SourceState, SourceStateMachine
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.hash import compute_content_hash
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()


class ArxivRssCollector(BaseCollector):
    """Collector for arXiv RSS/Atom feeds.

    Extends the base RSS collector with arXiv-specific URL normalization
    and ID extraction. All arXiv URLs are normalized to canonical /abs/<id> format.

    Supported feeds:
    - https://rss.arxiv.org/rss/cs.AI
    - https://rss.arxiv.org/rss/cs.LG
    - https://rss.arxiv.org/rss/cs.CL
    - https://rss.arxiv.org/rss/stat.ML
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
    ) -> None:
        """Initialize the arXiv RSS collector.

        Args:
            strip_params: URL parameters to strip (not used for arXiv).
            run_id: Run identifier for logging.
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._metrics = ArxivMetrics.get_instance()

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect items from an arXiv RSS feed.

        Args:
            source_config: Configuration for the source.
            http_client: HTTP client for fetching.
            now: Current timestamp for consistency.

        Returns:
            CollectorResult with items and status.
        """
        category = get_arxiv_category_from_url(source_config.url)
        log = logger.bind(
            component="arxiv",
            run_id=self._run_id,
            source_id=source_config.id,
            mode="rss",
            category=category,
        )

        state_machine = SourceStateMachine(
            source_id=source_config.id,
            run_id=self._run_id,
        )

        parse_warnings: list[str] = []

        try:
            state_machine.to_fetching()

            result = http_client.fetch(
                source_id=source_config.id,
                url=source_config.url,
                extra_headers=source_config.headers or None,
            )

            if result.error:
                log.warning(
                    "fetch_failed",
                    error_class=(
                        result.error.error_class.value
                        if hasattr(result.error, "error_class")
                        else "unknown"
                    ),
                    status_code=result.status_code,
                )
                state_machine.to_failed()
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.FETCH,
                        message=str(result.error),
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            if result.cache_hit:
                log.info("cache_hit_no_changes")
                state_machine.to_parsing()
                state_machine.to_done()
                return CollectorResult(
                    items=[],
                    state=SourceState.SOURCE_DONE,
                )

            state_machine.to_parsing()

            feed = feedparser.parse(result.body_bytes)

            if feed.bozo and feed.bozo_exception:
                parse_warnings.append(f"Feed parsing warning: {feed.bozo_exception}")
                log.warning(
                    "feed_parse_warning",
                    bozo_exception=str(feed.bozo_exception),
                )
                self._metrics.record_error("malformed_atom")

            if not feed.entries:
                log.info("empty_feed")
                state_machine.to_done()
                return CollectorResult(
                    items=[],
                    parse_warnings=parse_warnings,
                    state=SourceState.SOURCE_DONE,
                )

            items = self._parse_entries(
                entries=feed.entries,
                source_config=source_config,
                category=category,
                parse_warnings=parse_warnings,
            )

            # Filter by time: only keep items published in the last 24 hours
            items = self.filter_items_by_time(
                items=items,
                now=now,
                lookback_hours=lookback_hours,
                source_id=source_config.id,
            )

            items = self.sort_items_deterministically(items)
            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )
            items = self.enforce_max_items(items, max_items)

            self._metrics.record_items(len(items), "rss", category)

            log.info(
                "collection_complete",
                items_emitted=len(items),
                parse_warnings_count=len(parse_warnings),
            )

            state_machine.to_done()
            return CollectorResult(
                items=items,
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_DONE,
            )

        except Exception as e:  # noqa: BLE001
            log.warning("unexpected_error", error=str(e))
            state_machine.to_failed()
            return CollectorResult(
                items=[],
                error=ErrorRecord(
                    error_class=CollectorErrorClass.PARSE,
                    message=f"Unexpected error: {e}",
                    source_id=source_config.id,
                ),
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_FAILED,
            )

    def _parse_entries(
        self,
        entries: list[feedparser.FeedParserDict],
        source_config: SourceConfig,
        category: str | None,
        parse_warnings: list[str],
    ) -> list[Item]:
        """Parse feed entries into Items.

        Args:
            entries: List of feedparser entries.
            source_config: Source configuration.
            category: arXiv category from feed URL.
            parse_warnings: List to append warnings to.

        Returns:
            List of parsed Items.
        """
        items: list[Item] = []

        for entry in entries:
            try:
                item = self._parse_single_entry(
                    entry=entry,
                    source_config=source_config,
                    category=category,
                )
                if item:
                    items.append(item)
            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to parse entry: {e}")

        return items

    def _parse_single_entry(
        self,
        entry: feedparser.FeedParserDict,
        source_config: SourceConfig,
        category: str | None,
    ) -> Item | None:
        """Parse a single feed entry.

        Args:
            entry: Feedparser entry dict.
            source_config: Source configuration.
            category: arXiv category from feed URL.

        Returns:
            Item if parsing succeeded, None otherwise.
        """
        # Extract arXiv ID from entry
        arxiv_id = self._extract_arxiv_id_from_entry(entry)
        if not arxiv_id:
            return None

        # Normalize URL to canonical format
        canonical_url = f"https://arxiv.org/abs/{arxiv_id}"

        # Extract title
        title = entry.get("title", "").strip()
        if not title:
            title = f"Untitled arXiv paper {arxiv_id}"

        # Extract published date
        published_at, date_confidence = self._extract_date(entry)

        # Build raw_json
        raw_data = self._build_raw_data(entry, arxiv_id, category)
        raw_json, _ = self.truncate_raw_json(raw_data)

        # Compute content hash from arXiv-specific fields
        content_hash = self._compute_arxiv_hash(entry, arxiv_id)

        return Item(
            url=canonical_url,
            source_id=source_config.id,
            tier=source_config.tier,
            kind=source_config.kind.value,
            title=title,
            published_at=published_at,
            date_confidence=date_confidence,
            content_hash=content_hash,
            raw_json=raw_json,
        )

    def _extract_arxiv_id_from_entry(
        self,
        entry: feedparser.FeedParserDict,
    ) -> str | None:
        """Extract arXiv ID from a feed entry.

        Args:
            entry: Feedparser entry dict.

        Returns:
            arXiv ID, or None if not found.
        """
        # Try entry ID first (most reliable for arXiv feeds)
        entry_id = entry.get("id", "")
        arxiv_id = extract_arxiv_id(entry_id)
        if arxiv_id:
            return arxiv_id

        # Try link
        link = entry.get("link", "")
        arxiv_id = extract_arxiv_id(link)
        if arxiv_id:
            return arxiv_id

        # Try all links
        for link_entry in entry.get("links", []):
            link = link_entry.get("href", "")
            arxiv_id = extract_arxiv_id(link)
            if arxiv_id:
                return arxiv_id

        return None

    def _extract_date(
        self,
        entry: feedparser.FeedParserDict,
    ) -> tuple[datetime | None, DateConfidence]:
        """Extract publication date from entry.

        Args:
            entry: Feedparser entry dict.

        Returns:
            Tuple of (datetime or None, confidence level).
        """
        # Try published_parsed first
        if entry.get("published_parsed"):
            try:
                timestamp = mktime(entry.published_parsed)
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
                return dt, DateConfidence.HIGH
            except (ValueError, OverflowError):
                pass

        # Try updated_parsed
        if entry.get("updated_parsed"):
            try:
                timestamp = mktime(entry.updated_parsed)
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
                return dt, DateConfidence.MEDIUM
            except (ValueError, OverflowError):
                pass

        # Try parsing published string
        if entry.get("published"):
            try:
                dt = parsedate_to_datetime(entry.published)
                return dt.astimezone(UTC), DateConfidence.HIGH
            except (ValueError, TypeError):
                pass

        # Try parsing updated string
        if entry.get("updated"):
            try:
                dt = parsedate_to_datetime(entry.updated)
                return dt.astimezone(UTC), DateConfidence.MEDIUM
            except (ValueError, TypeError):
                pass

        return None, DateConfidence.LOW

    def _build_raw_data(
        self,
        entry: feedparser.FeedParserDict,
        arxiv_id: str,
        category: str | None,
    ) -> dict[str, Any]:
        """Build raw_json data from entry.

        Args:
            entry: Feedparser entry dict.
            arxiv_id: Extracted arXiv ID.
            category: arXiv category from feed URL.

        Returns:
            Dictionary of raw metadata.
        """
        raw_data: dict[str, Any] = {
            "arxiv_id": arxiv_id,
            "source": "rss",
        }

        if category:
            raw_data["feed_category"] = category

        # Add title
        title = entry.get("title", "")
        if title:
            raw_data["title"] = title

        # Add authors
        authors = entry.get("authors", [])
        if authors:
            raw_data["authors"] = [a.get("name", "") for a in authors if a.get("name")]

        # Add summary/abstract (truncated)
        summary = entry.get("summary", "") or entry.get("description", "")
        if summary:
            raw_data["abstract_snippet"] = summary[:500]

        # Add categories/tags
        tags = entry.get("tags", [])
        if tags:
            raw_data["categories"] = [t.get("term", "") for t in tags if t.get("term")]

        return raw_data

    def _compute_arxiv_hash(
        self,
        entry: feedparser.FeedParserDict,
        arxiv_id: str,
    ) -> str:
        """Compute content hash for arXiv entry.

        Hash is computed from: title, abstract_snippet, categories, updated_at.

        Args:
            entry: Feedparser entry dict.
            arxiv_id: arXiv ID.

        Returns:
            Content hash string.
        """
        title = entry.get("title", "")
        summary = entry.get("summary", "")[:200] if entry.get("summary") else ""
        tags = entry.get("tags", [])
        categories = ",".join(sorted(t.get("term", "") for t in tags if t.get("term")))

        extra = {}
        if summary:
            extra["abstract_snippet"] = summary
        if categories:
            extra["categories"] = categories

        # Include updated_at if available
        if entry.get("updated"):
            extra["updated_at"] = entry.get("updated")

        return compute_content_hash(
            title=title,
            url=f"https://arxiv.org/abs/{arxiv_id}",
            extra=extra if extra else None,
        )
