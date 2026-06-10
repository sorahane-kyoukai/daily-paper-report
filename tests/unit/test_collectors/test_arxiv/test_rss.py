"""Unit tests for arXiv RSS collector."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.collectors.arxiv.metrics import ArxivMetrics
from src.collectors.arxiv.rss import ArxivRssCollector
from src.collectors.state_machine import SourceState
from src.features.config.schemas.sources import SourceConfig, SourceKind, SourceMethod
from src.features.fetch.client import HttpFetcher
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult


# Timestamp matching sample data dates - used for run_timestamp in tests
# to ensure items aren't filtered out by 24-hour lookback window.
SAMPLE_DATA_TIMESTAMP = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)

# Sample arXiv RSS feed content
SAMPLE_RSS_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
  <title>cs.AI updates on arXiv.org</title>
  <link>https://arxiv.org/</link>
</channel>
<item rdf:about="http://arxiv.org/abs/2401.12345">
  <title>Test Paper: A Deep Learning Approach</title>
  <link>http://arxiv.org/abs/2401.12345</link>
  <description>This is a test abstract for the paper.</description>
  <dc:creator>Test Author</dc:creator>
  <dc:date>2024-01-15T10:00:00Z</dc:date>
</item>
<item rdf:about="http://arxiv.org/abs/2401.12346">
  <title>Another Test Paper: Transformer Architecture</title>
  <link>http://arxiv.org/abs/2401.12346</link>
  <description>Another test abstract.</description>
  <dc:creator>Another Author</dc:creator>
  <dc:date>2024-01-15T08:00:00Z</dc:date>
</item>
</rdf:RDF>"""


SAMPLE_ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>cs.AI updates on arXiv.org</title>
  <link href="https://arxiv.org/"/>
  <entry>
    <id>http://arxiv.org/abs/2401.12345</id>
    <title>Test Paper: A Deep Learning Approach</title>
    <link href="http://arxiv.org/abs/2401.12345"/>
    <summary>This is a test abstract for the paper.</summary>
    <author><name>Test Author</name></author>
    <published>2024-01-15T10:00:00Z</published>
    <updated>2024-01-15T12:00:00Z</updated>
    <category term="cs.AI"/>
  </entry>
</feed>"""


def make_source_config(
    source_id: str = "arxiv-cs-ai",
    url: str = "https://rss.arxiv.org/rss/cs.AI",
    max_items: int = 100,
) -> SourceConfig:
    """Create a test source configuration."""
    return SourceConfig(
        id=source_id,
        name="arXiv cs.AI",
        url=url,
        method=SourceMethod.RSS_ATOM,
        tier=1,
        kind=SourceKind.PAPER,
        max_items=max_items,
    )


class TestArxivRssCollector:
    """Tests for ArxivRssCollector class."""

    def setup_method(self) -> None:
        """Reset metrics before each test."""
        ArxivMetrics.reset()

    def test_successful_collection(self) -> None:
        """Test successful RSS feed collection."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source_config.url,
            headers={},
            body_bytes=SAMPLE_ATOM_FEED,
            cache_hit=False,
            error=None,
        )

        now = SAMPLE_DATA_TIMESTAMP
        result = collector.collect(source_config, mock_client, now)

        assert result.success
        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 1
        assert result.items[0].url == "https://arxiv.org/abs/2401.12345"

    def test_canonical_url_format(self) -> None:
        """Test that URLs are normalized to canonical format."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source_config.url,
            headers={},
            body_bytes=SAMPLE_ATOM_FEED,
            cache_hit=False,
            error=None,
        )

        result = collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        for item in result.items:
            assert item.url.startswith("https://arxiv.org/abs/")
            # Should not contain version suffix
            assert "v1" not in item.url
            assert "v2" not in item.url

    def test_cache_hit_returns_empty(self) -> None:
        """Test that cache hit returns empty result."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=304,
            final_url=source_config.url,
            headers={},
            body_bytes=b"",
            cache_hit=True,
            error=None,
        )

        result = collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        assert result.success
        assert len(result.items) == 0

    def test_fetch_error_returns_failed_state(self) -> None:
        """Test that fetch error returns failed state."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=500,
            final_url=source_config.url,
            headers={},
            body_bytes=b"",
            cache_hit=False,
            error=FetchError(
                error_class=FetchErrorClass.HTTP_5XX,
                message="Server error",
                status_code=500,
            ),
        )

        result = collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        assert not result.success
        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None

    def test_empty_feed_returns_success(self) -> None:
        """Test that empty feed returns success with no items."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        empty_feed = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Empty Feed</title>
        </feed>"""

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source_config.url,
            headers={},
            body_bytes=empty_feed,
            cache_hit=False,
            error=None,
        )

        result = collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        assert result.success
        assert len(result.items) == 0

    def test_max_items_enforced(self) -> None:
        """Test that max_items limit is enforced."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config(max_items=1)

        # Feed with 2 entries - dates within 24h of SAMPLE_DATA_TIMESTAMP
        feed_with_two = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2401.12345</id>
            <title>Paper 1</title>
            <link href="http://arxiv.org/abs/2401.12345"/>
            <published>2024-01-15T10:00:00Z</published>
          </entry>
          <entry>
            <id>http://arxiv.org/abs/2401.12346</id>
            <title>Paper 2</title>
            <link href="http://arxiv.org/abs/2401.12346"/>
            <published>2024-01-15T08:00:00Z</published>
          </entry>
        </feed>"""

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source_config.url,
            headers={},
            body_bytes=feed_with_two,
            cache_hit=False,
            error=None,
        )

        result = collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        assert result.success
        assert len(result.items) == 1

    def test_metrics_recorded(self) -> None:
        """Test that metrics are recorded."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source_config.url,
            headers={},
            body_bytes=SAMPLE_ATOM_FEED,
            cache_hit=False,
            error=None,
        )

        collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        metrics = ArxivMetrics.get_instance()
        assert metrics.get_items_total("rss", "cs.AI") == 1

    def test_date_extraction_high_confidence(self) -> None:
        """Test that published date gives high confidence."""
        collector = ArxivRssCollector(run_id="test")
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source_config.url,
            headers={},
            body_bytes=SAMPLE_ATOM_FEED,
            cache_hit=False,
            error=None,
        )

        result = collector.collect(source_config, mock_client, SAMPLE_DATA_TIMESTAMP)

        assert result.items[0].published_at is not None
        from src.features.store.models import DateConfidence

        assert result.items[0].date_confidence == DateConfidence.HIGH
