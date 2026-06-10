"""Unit tests for base collector functionality."""

from datetime import UTC, datetime

from src.collectors.base import RAW_JSON_MAX_SIZE, BaseCollector, CollectorResult
from src.collectors.state_machine import SourceState
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.models import DateConfidence, Item


class ConcreteCollector(BaseCollector):
    """Concrete implementation for testing."""

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        return CollectorResult(items=[], state=SourceState.SOURCE_DONE)


class TestCollectorResult:
    """Tests for CollectorResult."""

    def test_empty_result(self) -> None:
        """Create an empty result."""
        result = CollectorResult(items=[])
        assert result.items == []
        assert result.parse_warnings == []
        assert result.error is None
        assert result.state == SourceState.SOURCE_DONE
        assert result.success is True
        assert result.items_count == 0

    def test_failed_result(self) -> None:
        """Create a failed result."""
        result = CollectorResult(
            items=[],
            state=SourceState.SOURCE_FAILED,
        )
        assert result.success is False


class TestBaseCollectorUrlCanonicalization:
    """Tests for URL canonicalization in BaseCollector."""

    def test_canonicalize_absolute_url(self) -> None:
        """Canonicalize an absolute URL."""
        collector = ConcreteCollector()
        url = collector.canonicalize_url("https://example.com/path")
        assert url == "https://example.com/path"

    def test_canonicalize_relative_url(self) -> None:
        """Canonicalize a relative URL with base."""
        collector = ConcreteCollector()
        url = collector.canonicalize_url(
            "/article/123",
            base_url="https://example.com/blog/",
        )
        assert url == "https://example.com/article/123"

    def test_canonicalize_strips_tracking_params(self) -> None:
        """Canonicalize strips UTM parameters."""
        collector = ConcreteCollector()
        url = collector.canonicalize_url(
            "https://example.com/page?utm_source=twitter&id=123"
        )
        assert "utm_source" not in url
        assert "id=123" in url

    def test_canonicalize_removes_fragment(self) -> None:
        """Canonicalize removes URL fragments."""
        collector = ConcreteCollector()
        url = collector.canonicalize_url("https://example.com/page#section")
        assert "#section" not in url

    def test_canonicalize_normalizes_arxiv(self) -> None:
        """Canonicalize normalizes arXiv URLs to /abs/ form."""
        collector = ConcreteCollector()

        # PDF URL
        url = collector.canonicalize_url("https://arxiv.org/pdf/2301.12345.pdf")
        assert url == "https://arxiv.org/abs/2301.12345"

        # ar5iv URL
        url = collector.canonicalize_url("https://ar5iv.labs.arxiv.org/html/2301.12345")
        assert url == "https://arxiv.org/abs/2301.12345"


class TestBaseCollectorUrlValidation:
    """Tests for URL validation in BaseCollector."""

    def test_validate_http_url(self) -> None:
        """HTTP URL is valid."""
        collector = ConcreteCollector()
        assert collector.validate_url("http://example.com") is True

    def test_validate_https_url(self) -> None:
        """HTTPS URL is valid."""
        collector = ConcreteCollector()
        assert collector.validate_url("https://example.com") is True

    def test_reject_javascript_url(self) -> None:
        """JavaScript URL is invalid."""
        collector = ConcreteCollector()
        assert collector.validate_url("javascript:void(0)") is False

    def test_reject_mailto_url(self) -> None:
        """Mailto URL is invalid."""
        collector = ConcreteCollector()
        assert collector.validate_url("mailto:test@example.com") is False

    def test_reject_relative_url(self) -> None:
        """Relative URL is invalid."""
        collector = ConcreteCollector()
        assert collector.validate_url("/path/to/page") is False


class TestBaseCollectorRawJsonTruncation:
    """Tests for raw_json truncation in BaseCollector."""

    def test_small_json_not_truncated(self) -> None:
        """Small raw_json is not truncated."""
        collector = ConcreteCollector()
        data = {"title": "Test", "url": "https://example.com"}
        json_str, truncated = collector.truncate_raw_json(data)
        assert truncated is False
        assert "raw_truncated" not in json_str

    def test_large_json_truncated(self) -> None:
        """Large raw_json is truncated."""
        collector = ConcreteCollector()
        # Create data larger than RAW_JSON_MAX_SIZE
        data = {"content": "x" * (RAW_JSON_MAX_SIZE + 1000)}
        json_str, truncated = collector.truncate_raw_json(data)
        assert truncated is True
        assert "raw_truncated" in json_str
        assert len(json_str.encode("utf-8")) <= RAW_JSON_MAX_SIZE

    def test_sanitizes_sensitive_keys(self) -> None:
        """Sensitive keys are removed from raw_json."""
        collector = ConcreteCollector()
        data = {
            "title": "Test",
            "authorization": "Bearer secret123",
            "token": "abc123",
            "api_key": "key456",
        }
        json_str, _ = collector.truncate_raw_json(data)
        assert "authorization" not in json_str.lower()
        assert "secret123" not in json_str
        assert "token" not in json_str.lower()
        assert "api_key" not in json_str.lower()
        assert "title" in json_str


class TestBaseCollectorStableOrdering:
    """Tests for deterministic item ordering in BaseCollector."""

    def test_sort_by_date_descending(self) -> None:
        """Items are sorted by published_at descending."""
        collector = ConcreteCollector()

        items = [
            Item(
                url="https://example.com/1",
                source_id="test",
                tier=0,
                kind="blog",
                title="Older",
                published_at=datetime(2024, 1, 1, tzinfo=UTC),
                date_confidence=DateConfidence.HIGH,
                content_hash="hash1",
                raw_json="{}",
            ),
            Item(
                url="https://example.com/2",
                source_id="test",
                tier=0,
                kind="blog",
                title="Newer",
                published_at=datetime(2024, 6, 1, tzinfo=UTC),
                date_confidence=DateConfidence.HIGH,
                content_hash="hash2",
                raw_json="{}",
            ),
        ]

        sorted_items = collector.sort_items_deterministically(items)
        assert sorted_items[0].title == "Newer"
        assert sorted_items[1].title == "Older"

    def test_nulls_last(self) -> None:
        """Items without dates come after dated items."""
        collector = ConcreteCollector()

        items = [
            Item(
                url="https://example.com/no-date",
                source_id="test",
                tier=0,
                kind="blog",
                title="No Date",
                published_at=None,
                date_confidence=DateConfidence.LOW,
                content_hash="hash1",
                raw_json="{}",
            ),
            Item(
                url="https://example.com/has-date",
                source_id="test",
                tier=0,
                kind="blog",
                title="Has Date",
                published_at=datetime(2024, 1, 1, tzinfo=UTC),
                date_confidence=DateConfidence.HIGH,
                content_hash="hash2",
                raw_json="{}",
            ),
        ]

        sorted_items = collector.sort_items_deterministically(items)
        assert sorted_items[0].title == "Has Date"
        assert sorted_items[1].title == "No Date"

    def test_url_tiebreaker(self) -> None:
        """Items with same date are sorted by URL ascending."""
        collector = ConcreteCollector()
        same_date = datetime(2024, 1, 1, tzinfo=UTC)

        items = [
            Item(
                url="https://example.com/z",
                source_id="test",
                tier=0,
                kind="blog",
                title="Z",
                published_at=same_date,
                date_confidence=DateConfidence.HIGH,
                content_hash="hash1",
                raw_json="{}",
            ),
            Item(
                url="https://example.com/a",
                source_id="test",
                tier=0,
                kind="blog",
                title="A",
                published_at=same_date,
                date_confidence=DateConfidence.HIGH,
                content_hash="hash2",
                raw_json="{}",
            ),
        ]

        sorted_items = collector.sort_items_deterministically(items)
        assert sorted_items[0].url == "https://example.com/a"
        assert sorted_items[1].url == "https://example.com/z"

    def test_deterministic_ordering(self) -> None:
        """Sorting is deterministic across multiple calls."""
        collector = ConcreteCollector()

        items = [
            Item(
                url=f"https://example.com/{i}",
                source_id="test",
                tier=0,
                kind="blog",
                title=f"Item {i}",
                published_at=datetime(2024, 1, i + 1, tzinfo=UTC)
                if i % 2 == 0
                else None,
                date_confidence=DateConfidence.HIGH
                if i % 2 == 0
                else DateConfidence.LOW,
                content_hash=f"hash{i}",
                raw_json="{}",
            )
            for i in range(10)
        ]

        # Sort multiple times
        sorted1 = collector.sort_items_deterministically(items.copy())
        sorted2 = collector.sort_items_deterministically(items.copy())
        sorted3 = collector.sort_items_deterministically(list(reversed(items)))

        # All orderings should be identical
        assert [i.url for i in sorted1] == [i.url for i in sorted2]
        assert [i.url for i in sorted1] == [i.url for i in sorted3]


class TestBaseCollectorMaxItems:
    """Tests for max_items_per_source enforcement."""

    def test_enforce_max_items(self) -> None:
        """Max items limit is enforced."""
        collector = ConcreteCollector()

        items = [
            Item(
                url=f"https://example.com/{i}",
                source_id="test",
                tier=0,
                kind="blog",
                title=f"Item {i}",
                published_at=datetime(2024, 1, i + 1, tzinfo=UTC),
                date_confidence=DateConfidence.HIGH,
                content_hash=f"hash{i}",
                raw_json="{}",
            )
            for i in range(20)
        ]

        truncated = collector.enforce_max_items(items, max_items=5)
        assert len(truncated) == 5

    def test_max_items_zero_returns_all(self) -> None:
        """Max items of 0 returns all items."""
        collector = ConcreteCollector()

        items = [
            Item(
                url=f"https://example.com/{i}",
                source_id="test",
                tier=0,
                kind="blog",
                title=f"Item {i}",
                published_at=None,
                date_confidence=DateConfidence.LOW,
                content_hash=f"hash{i}",
                raw_json="{}",
            )
            for i in range(10)
        ]

        result = collector.enforce_max_items(items, max_items=0)
        assert len(result) == 10

    def test_max_items_greater_than_count(self) -> None:
        """Max items greater than count returns all items."""
        collector = ConcreteCollector()

        items = [
            Item(
                url=f"https://example.com/{i}",
                source_id="test",
                tier=0,
                kind="blog",
                title=f"Item {i}",
                published_at=None,
                date_confidence=DateConfidence.LOW,
                content_hash=f"hash{i}",
                raw_json="{}",
            )
            for i in range(5)
        ]

        result = collector.enforce_max_items(items, max_items=100)
        assert len(result) == 5
