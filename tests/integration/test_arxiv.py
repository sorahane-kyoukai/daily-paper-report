"""Integration tests for arXiv collectors."""

import json
from datetime import UTC, datetime

import pytest

from src.collectors.arxiv.deduper import ArxivDeduplicator
from src.collectors.arxiv.metrics import ArxivMetrics
from src.collectors.arxiv.rss import ArxivRssCollector
from src.features.store.models import DateConfidence, Item
from tests.helpers.time import FIXED_NOW


# Sample RSS feed for cs.AI
CS_AI_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>cs.AI updates on arXiv.org</title>
  <entry>
    <id>http://arxiv.org/abs/2401.12345</id>
    <title>Shared Paper: Appears in Both</title>
    <summary>This paper is in both cs.AI and cs.LG.</summary>
    <author><name>Author One</name></author>
    <published>2024-01-15T10:00:00Z</published>
    <updated>2024-01-15T12:00:00Z</updated>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.11111</id>
    <title>AI Only Paper</title>
    <summary>This paper is only in cs.AI.</summary>
    <author><name>Author Two</name></author>
    <published>2024-01-14T10:00:00Z</published>
  </entry>
</feed>"""

# Sample RSS feed for cs.LG
CS_LG_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>cs.LG updates on arXiv.org</title>
  <entry>
    <id>http://arxiv.org/abs/2401.12345</id>
    <title>Shared Paper: Appears in Both</title>
    <summary>This paper is in both cs.AI and cs.LG.</summary>
    <author><name>Author One</name></author>
    <published>2024-01-15T08:00:00Z</published>
    <updated>2024-01-15T12:00:00Z</updated>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.22222</id>
    <title>LG Only Paper</title>
    <summary>This paper is only in cs.LG.</summary>
    <author><name>Author Three</name></author>
    <published>2024-01-13T10:00:00Z</published>
  </entry>
</feed>"""

# Sample API response
API_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v2</id>
    <title>Shared Paper: Appears in Both</title>
    <summary>This paper is in both cs.AI and cs.LG. API has more detail.</summary>
    <author><name>Author One</name></author>
    <published>2024-01-15T06:00:00Z</published>
    <updated>2024-01-16T12:00:00Z</updated>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.33333v1</id>
    <title>API Only Paper</title>
    <summary>This paper only appears in API query.</summary>
    <author><name>Author Four</name></author>
    <published>2024-01-12T10:00:00Z</published>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>"""


def make_mock_client(responses: dict[str, bytes]) -> object:
    """Create a mock HTTP client that returns different responses by URL pattern."""

    class MockFetchResult:
        def __init__(self, body: bytes) -> None:
            self.status_code = 200
            self.final_url = ""
            self.headers: dict[str, str] = {}
            self.body_bytes = body
            self.cache_hit = False
            self.error = None

    class MockHttpClient:
        def fetch(
            self,
            source_id: str,
            url: str,
            extra_headers: dict[str, str] | None = None,
        ) -> MockFetchResult:
            for pattern, body in responses.items():
                if pattern in url:
                    result = MockFetchResult(body)
                    result.final_url = url
                    return result
            return MockFetchResult(b"")

    return MockHttpClient()


@pytest.fixture
def reset_metrics() -> None:
    """Reset metrics before each test."""
    ArxivMetrics.reset()


class TestCrossSourceDeduplication:
    """Integration tests for cross-source deduplication."""

    def test_same_id_from_multiple_rss_feeds_produces_one_item(
        self, reset_metrics: None
    ) -> None:
        """Test that same arXiv ID from multiple RSS feeds produces one item."""
        from src.features.config.schemas.sources import (
            SourceConfig,
            SourceKind,
            SourceMethod,
        )

        # Create collectors
        rss_collector = ArxivRssCollector(run_id="test")

        # Mock client
        mock_client = make_mock_client(
            {
                "cs.AI": CS_AI_FEED,
                "cs.LG": CS_LG_FEED,
            }
        )

        # Collect from both feeds
        cs_ai_config = SourceConfig(
            id="arxiv-cs-ai",
            name="arXiv cs.AI",
            url="https://rss.arxiv.org/rss/cs.AI",
            method=SourceMethod.RSS_ATOM,
            tier=1,
            kind=SourceKind.PAPER,
        )
        cs_lg_config = SourceConfig(
            id="arxiv-cs-lg",
            name="arXiv cs.LG",
            url="https://rss.arxiv.org/rss/cs.LG",
            method=SourceMethod.RSS_ATOM,
            tier=1,
            kind=SourceKind.PAPER,
        )

        now = FIXED_NOW
        ai_result = rss_collector.collect(cs_ai_config, mock_client, now)  # type: ignore[arg-type]
        lg_result = rss_collector.collect(cs_lg_config, mock_client, now)  # type: ignore[arg-type]

        # Combine all items
        all_items = ai_result.items + lg_result.items

        # Should have 4 items before deduplication
        # cs.AI: 2401.12345, 2401.11111
        # cs.LG: 2401.12345, 2401.22222
        assert len(all_items) == 4

        # Deduplicate
        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate(all_items)

        # Should have 3 unique items
        assert result.final_count == 3
        assert result.deduped_count == 1

        # Verify unique arXiv IDs
        urls = {item.url for item in result.items}
        assert "https://arxiv.org/abs/2401.12345" in urls
        assert "https://arxiv.org/abs/2401.11111" in urls
        assert "https://arxiv.org/abs/2401.22222" in urls

    def test_api_source_preferred_over_rss(self, reset_metrics: None) -> None:
        """Test that API source is preferred over RSS when merging."""
        # Create items from different sources
        rss_item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv-cs-ai",
            tier=1,
            kind="paper",
            title="RSS Title",
            published_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            date_confidence=DateConfidence.HIGH,
            content_hash="abc123",
            raw_json=json.dumps({"arxiv_id": "2401.12345", "source": "rss"}),
        )

        api_item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv-api",
            tier=0,
            kind="paper",
            title="API Title",
            published_at=datetime(2024, 1, 15, 6, 0, 0, tzinfo=UTC),
            date_confidence=DateConfidence.HIGH,
            content_hash="def456",
            raw_json=json.dumps({"arxiv_id": "2401.12345", "source": "api"}),
        )

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([rss_item, api_item])

        assert result.final_count == 1

        # The merged item should have info about being merged
        merged_raw = json.loads(result.items[0].raw_json)
        assert "merged_from_sources" in merged_raw

    def test_timestamp_preference_api_over_rss(self, reset_metrics: None) -> None:
        """Test that API timestamps are preferred when they differ significantly."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        # RSS says published at noon
        rss_item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv-cs-ai",
            tier=1,
            kind="paper",
            title="Test Paper",
            published_at=now,
            date_confidence=DateConfidence.HIGH,
            content_hash="abc123",
            raw_json=json.dumps({"arxiv_id": "2401.12345", "source": "rss"}),
        )

        # API says published 3 days earlier (significant difference)
        from datetime import timedelta

        api_time = now - timedelta(days=3)
        api_item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv-api",
            tier=0,
            kind="paper",
            title="Test Paper",
            published_at=api_time,
            date_confidence=DateConfidence.HIGH,
            content_hash="def456",
            raw_json=json.dumps({"arxiv_id": "2401.12345", "source": "api"}),
        )

        deduper = ArxivDeduplicator(run_id="test")
        result = deduper.deduplicate([rss_item, api_item])

        assert result.final_count == 1
        # Should be marked as medium confidence due to timestamp difference
        assert result.items[0].date_confidence == DateConfidence.MEDIUM

        # Should have timestamp note in raw_json
        merged_raw = json.loads(result.items[0].raw_json)
        assert "timestamp_note" in merged_raw


class TestIdempotency:
    """Integration tests for idempotent ingestion."""

    def test_repeated_ingestion_produces_same_items(self, reset_metrics: None) -> None:
        """Test that repeated ingestion produces identical items."""
        from src.features.config.schemas.sources import (
            SourceConfig,
            SourceKind,
            SourceMethod,
        )

        rss_collector = ArxivRssCollector(run_id="test")

        mock_client = make_mock_client({"cs.AI": CS_AI_FEED})

        config = SourceConfig(
            id="arxiv-cs-ai",
            name="arXiv cs.AI",
            url="https://rss.arxiv.org/rss/cs.AI",
            method=SourceMethod.RSS_ATOM,
            tier=1,
            kind=SourceKind.PAPER,
        )

        now = FIXED_NOW

        # First ingestion
        result1 = rss_collector.collect(config, mock_client, now)  # type: ignore[arg-type]

        # Reset metrics to get fresh instance
        ArxivMetrics.reset()

        # Second ingestion
        result2 = rss_collector.collect(config, mock_client, now)  # type: ignore[arg-type]

        # Should produce identical items
        assert len(result1.items) == len(result2.items)

        for item1, item2 in zip(result1.items, result2.items, strict=True):
            assert item1.url == item2.url
            assert item1.title == item2.title
            assert item1.content_hash == item2.content_hash


class TestCanonicalUrlFormat:
    """Integration tests for URL canonicalization."""

    def test_all_urls_use_canonical_format(self, reset_metrics: None) -> None:
        """Test that all collected URLs use canonical abs format."""
        from src.features.config.schemas.sources import (
            SourceConfig,
            SourceKind,
            SourceMethod,
        )

        rss_collector = ArxivRssCollector(run_id="test")

        mock_client = make_mock_client({"cs.AI": CS_AI_FEED})

        config = SourceConfig(
            id="arxiv-cs-ai",
            name="arXiv cs.AI",
            url="https://rss.arxiv.org/rss/cs.AI",
            method=SourceMethod.RSS_ATOM,
            tier=1,
            kind=SourceKind.PAPER,
        )

        result = rss_collector.collect(config, mock_client, FIXED_NOW)  # type: ignore[arg-type]

        for item in result.items:
            # Must start with canonical prefix
            assert item.url.startswith("https://arxiv.org/abs/")
            # Must not have version suffix
            assert not any(f"v{i}" in item.url for i in range(1, 10))
            # Must not be pdf or html variant
            assert "/pdf/" not in item.url
            assert "/html/" not in item.url


class TestMetricsIntegration:
    """Integration tests for metrics recording."""

    def test_full_pipeline_records_metrics(self, reset_metrics: None) -> None:
        """Test that full pipeline records all expected metrics."""
        from src.features.config.schemas.sources import (
            SourceConfig,
            SourceKind,
            SourceMethod,
        )

        rss_collector = ArxivRssCollector(run_id="test")

        mock_client = make_mock_client(
            {
                "cs.AI": CS_AI_FEED,
                "cs.LG": CS_LG_FEED,
            }
        )

        configs = [
            SourceConfig(
                id="arxiv-cs-ai",
                name="arXiv cs.AI",
                url="https://rss.arxiv.org/rss/cs.AI",
                method=SourceMethod.RSS_ATOM,
                tier=1,
                kind=SourceKind.PAPER,
            ),
            SourceConfig(
                id="arxiv-cs-lg",
                name="arXiv cs.LG",
                url="https://rss.arxiv.org/rss/cs.LG",
                method=SourceMethod.RSS_ATOM,
                tier=1,
                kind=SourceKind.PAPER,
            ),
        ]

        all_items = []
        now = FIXED_NOW

        for config in configs:
            result = rss_collector.collect(config, mock_client, now)  # type: ignore[arg-type]
            all_items.extend(result.items)

        # Deduplicate
        deduper = ArxivDeduplicator(run_id="test")
        deduper.deduplicate(all_items)

        # Check metrics
        metrics = ArxivMetrics.get_instance()
        snapshot = metrics.get_snapshot()

        # Should have items recorded for both categories
        # TypedDict provides type-safe access
        assert snapshot["items_by_mode_category"]["rss:cs.AI"] == 2
        assert snapshot["items_by_mode_category"]["rss:cs.LG"] == 2

        # Should have deduplication count
        assert snapshot["deduped_total"] == 1
