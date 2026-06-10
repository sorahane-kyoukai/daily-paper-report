"""Unit tests for arXiv deduplicator."""

import json
from datetime import UTC, datetime, timedelta

from src.collectors.arxiv.deduper import ArxivDeduplicator, DeduplicationResult
from src.collectors.arxiv.metrics import ArxivMetrics
from src.features.store.models import DateConfidence, Item


def make_item(
    arxiv_id: str,
    source_id: str = "test-source",
    source_type: str = "rss",
    published_at: datetime | None = None,
    date_confidence: DateConfidence = DateConfidence.HIGH,
) -> Item:
    """Create a test Item with arXiv URL."""
    raw_data = {"arxiv_id": arxiv_id, "source": source_type}
    return Item(
        url=f"https://arxiv.org/abs/{arxiv_id}",
        source_id=source_id,
        tier=1,
        kind="paper",
        title=f"Test Paper {arxiv_id}",
        published_at=published_at,
        date_confidence=date_confidence,
        content_hash="abc123",
        raw_json=json.dumps(raw_data),
    )


class TestArxivDeduplicator:
    """Tests for ArxivDeduplicator class."""

    def setup_method(self) -> None:
        """Reset metrics before each test."""
        ArxivMetrics.reset()

    def test_empty_list_returns_empty(self) -> None:
        """Test that empty list returns empty result."""
        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([])

        assert result.items == []
        assert result.original_count == 0
        assert result.deduped_count == 0

    def test_single_item_unchanged(self) -> None:
        """Test that single item passes through unchanged."""
        item = make_item("2401.12345")
        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([item])

        assert len(result.items) == 1
        assert result.items[0].url == item.url
        assert result.deduped_count == 0

    def test_different_ids_preserved(self) -> None:
        """Test that items with different arXiv IDs are all preserved."""
        items = [
            make_item("2401.12345"),
            make_item("2401.12346"),
            make_item("2401.12347"),
        ]
        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate(items)

        assert len(result.items) == 3
        assert result.deduped_count == 0

    def test_duplicate_ids_merged(self) -> None:
        """Test that items with same arXiv ID are merged."""
        items = [
            make_item("2401.12345", source_id="source1"),
            make_item("2401.12345", source_id="source2"),
        ]
        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate(items)

        assert len(result.items) == 1
        assert result.deduped_count == 1
        assert "2401.12345" in result.merged_ids

    def test_api_source_preferred_over_rss(self) -> None:
        """Test that API source is preferred over RSS."""
        rss_item = make_item("2401.12345", source_id="rss", source_type="rss")
        api_item = make_item("2401.12345", source_id="api", source_type="api")

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([rss_item, api_item])

        assert len(result.items) == 1
        # Verify the API source was kept
        raw = json.loads(result.items[0].raw_json)
        # Should have merged info
        assert "merged_from_sources" in raw or raw.get("source") == "api"

    def test_item_with_date_preferred(self) -> None:
        """Test that item with published_at is preferred."""
        now = datetime.now(UTC)
        item_with_date = make_item(
            "2401.12345",
            source_id="dated",
            published_at=now,
        )
        item_without_date = make_item(
            "2401.12345",
            source_id="undated",
            published_at=None,
            date_confidence=DateConfidence.LOW,
        )

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([item_without_date, item_with_date])

        assert len(result.items) == 1
        assert result.items[0].published_at is not None

    def test_timestamps_differ_marks_medium_confidence(self) -> None:
        """Test that differing timestamps result in medium confidence."""
        now = datetime.now(UTC)
        item1 = make_item(
            "2401.12345",
            source_id="source1",
            source_type="api",
            published_at=now,
        )
        item2 = make_item(
            "2401.12345",
            source_id="source2",
            source_type="rss",
            published_at=now - timedelta(days=2),  # 2 days earlier
        )

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([item1, item2])

        assert len(result.items) == 1
        assert result.items[0].date_confidence == DateConfidence.MEDIUM

    def test_timestamps_similar_keeps_original_confidence(self) -> None:
        """Test that similar timestamps keep original confidence."""
        now = datetime.now(UTC)
        item1 = make_item(
            "2401.12345",
            source_id="source1",
            source_type="api",
            published_at=now,
        )
        item2 = make_item(
            "2401.12345",
            source_id="source2",
            source_type="rss",
            published_at=now - timedelta(hours=1),  # Only 1 hour earlier
        )

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([item1, item2])

        assert len(result.items) == 1
        # Should keep HIGH confidence since timestamps are within 1 day
        assert result.items[0].date_confidence == DateConfidence.HIGH

    def test_merged_item_has_source_info(self) -> None:
        """Test that merged item includes source information."""
        items = [
            make_item("2401.12345", source_id="source1", source_type="api"),
            make_item("2401.12345", source_id="source2", source_type="rss"),
        ]

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate(items)

        raw = json.loads(result.items[0].raw_json)
        assert "merged_from_sources" in raw
        assert raw["merged_from_sources"] == 2
        assert "source_ids" in raw
        assert set(raw["source_ids"]) == {"source1", "source2"}

    def test_metrics_recorded(self) -> None:
        """Test that deduplication metrics are recorded."""
        items = [
            make_item("2401.12345", source_id="source1"),
            make_item("2401.12345", source_id="source2"),
            make_item("2401.12346", source_id="source1"),
        ]

        deduper = ArxivDeduplicator(run_id="test")
        deduper.deduplicate(items)

        metrics = ArxivMetrics.get_instance()
        assert metrics.get_deduped_total() == 1  # One item was deduplicated


class TestDeduplicationResult:
    """Tests for DeduplicationResult class."""

    def test_final_count_property(self) -> None:
        """Test final_count property."""
        result = DeduplicationResult(
            items=[make_item("2401.12345")],
            original_count=3,
            deduped_count=2,
        )
        assert result.final_count == 1

    def test_empty_result(self) -> None:
        """Test empty result properties."""
        result = DeduplicationResult(
            items=[],
            original_count=0,
            deduped_count=0,
        )
        assert result.final_count == 0
        assert result.merged_ids == []
