"""Tests for RssAtomCollector."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.collectors.rss_atom import RssAtomCollector
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult


# Fixed timestamp for tests - sample data dates should be within 24h of this.
# Using a date far enough from midnight that typical test dates (noon) fit within window.
TEST_TIMESTAMP = datetime(2024, 1, 3, 18, 0, 0, tzinfo=UTC)


def make_source_config(
    source_id: str = "test-source",
    url: str = "https://example.com/feed.xml",
    max_items: int = 0,
) -> SourceConfig:
    """Create a test SourceConfig."""
    return SourceConfig(
        id=source_id,
        name="Test Source",
        url=url,
        method=SourceMethod.RSS_ATOM,
        kind=SourceKind.BLOG,
        tier=SourceTier.TIER_1,
        max_items=max_items,
    )


def make_fetch_result(
    body: bytes = b"",
    status_code: int = 200,
    cache_hit: bool = False,
    error: FetchError | None = None,
    final_url: str = "https://example.com/feed.xml",
) -> FetchResult:
    """Create a test FetchResult."""
    return FetchResult(
        status_code=status_code,
        final_url=final_url,
        body_bytes=body,
        cache_hit=cache_hit,
        headers={},
        error=error,
    )


class TestRssAtomCollectorInit:
    """Tests for RssAtomCollector initialization."""

    def test_init_default_params(self) -> None:
        """Collector initializes with default parameters."""
        collector = RssAtomCollector()
        assert collector._run_id == ""
        assert collector._strip_params is None

    def test_init_custom_params(self) -> None:
        """Collector accepts custom parameters."""
        collector = RssAtomCollector(
            strip_params=["utm_source", "utm_medium"],
            run_id="run-123",
        )
        assert collector._run_id == "run-123"
        assert collector._strip_params == ["utm_source", "utm_medium"]


class TestRssAtomCollectorFetchErrors:
    """Tests for fetch error handling."""

    def test_fetch_error_returns_failed_state(self) -> None:
        """Fetch error returns SOURCE_FAILED state."""
        collector = RssAtomCollector(run_id="test-run")
        source_config = make_source_config()
        http_client = MagicMock()
        http_client.fetch.return_value = make_fetch_result(
            error=FetchError(
                error_class=FetchErrorClass.CONNECTION_ERROR,
                message="Connection refused",
            ),
        )

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert result.state == SourceState.SOURCE_FAILED
        assert result.items == []
        assert result.error is not None


class TestRssAtomCollectorCacheHit:
    """Tests for cache hit handling."""

    def test_cache_hit_returns_empty_success(self) -> None:
        """304 cache hit returns success with no items."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()
        http_client.fetch.return_value = make_fetch_result(cache_hit=True)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert result.state == SourceState.SOURCE_DONE
        assert result.items == []
        assert result.error is None


class TestRssAtomCollectorParsing:
    """Tests for feed parsing."""

    def test_empty_feed_returns_empty_success(self) -> None:
        """Empty feed returns success with no items."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        # Empty RSS feed
        empty_feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Empty Feed</title>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=empty_feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert result.state == SourceState.SOURCE_DONE
        assert result.items == []

    def test_bozo_feed_adds_warning(self) -> None:
        """Malformed feed with bozo exception adds parse warning."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        # Malformed RSS that feedparser can partially parse
        malformed_feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Malformed Feed</title>
                <item>
                    <title>Item 1</title>
                    <link>https://example.com/1</link>
                </item>
            </channel>
        <!-- Missing closing tag -->"""

        http_client.fetch.return_value = make_fetch_result(body=malformed_feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        # Should still parse what it can
        assert result.state == SourceState.SOURCE_DONE

    def test_valid_rss_parses_items(self) -> None:
        """Valid RSS feed parses items correctly."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        valid_feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Article One</title>
                    <link>https://example.com/article-1</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                    <description>First article description</description>
                </item>
                <item>
                    <title>Article Two</title>
                    <link>https://example.com/article-2</link>
                    <pubDate>Wed, 03 Jan 2024 10:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=valid_feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 2
        # Sorted by date DESC
        assert result.items[0].title == "Article Two"
        assert result.items[1].title == "Article One"

    def test_atom_feed_parses_items(self) -> None:
        """Valid Atom feed parses items correctly."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        atom_feed = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Atom Feed</title>
            <entry>
                <title>Atom Article</title>
                <link href="https://example.com/atom-1" rel="alternate"/>
                <updated>2024-01-03T08:00:00Z</updated>
                <summary>Article summary</summary>
                <author><name>Test Author</name></author>
            </entry>
        </feed>"""

        http_client.fetch.return_value = make_fetch_result(body=atom_feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 1
        assert result.items[0].title == "Atom Article"


class TestRssAtomCollectorEntryParsing:
    """Tests for individual entry parsing."""

    def test_entry_without_link_skipped(self) -> None:
        """Entry without link is skipped."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>No Link Article</title>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>Has Link</title>
                    <link>https://example.com/has-link</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].title == "Has Link"

    def test_entry_with_alternate_link(self) -> None:
        """Entry uses alternate link when main link missing."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        atom_feed = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Alternate Link Article</title>
                <link href="https://example.com/alternate" rel="alternate"/>
                <updated>2024-01-03T08:00:00Z</updated>
            </entry>
        </feed>"""

        http_client.fetch.return_value = make_fetch_result(body=atom_feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].url == "https://example.com/alternate"

    def test_entry_with_first_link_fallback(self) -> None:
        """Entry uses first link as fallback."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        atom_feed = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>First Link Article</title>
                <link href="https://example.com/first" rel="enclosure"/>
                <updated>2024-01-03T08:00:00Z</updated>
            </entry>
        </feed>"""

        http_client.fetch.return_value = make_fetch_result(body=atom_feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].url == "https://example.com/first"

    def test_entry_without_title_gets_default(self) -> None:
        """Entry without title gets default title."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <link>https://example.com/no-title</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert "Untitled from" in result.items[0].title

    def test_entry_with_relative_url_resolved(self) -> None:
        """Entry with relative URL is resolved against base."""
        collector = RssAtomCollector()
        source_config = make_source_config(url="https://example.com/blog/feed.xml")
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Relative Link</title>
                    <link>/articles/post-1</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].url == "https://example.com/articles/post-1"

    def test_entry_with_invalid_url_skipped(self) -> None:
        """Entry with invalid URL (javascript:) is skipped."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>JS Link</title>
                    <link>javascript:void(0)</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>Valid Link</title>
                    <link>https://example.com/valid</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].title == "Valid Link"

    def test_entry_with_categories(self) -> None:
        """Entry with categories parses them correctly."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Tagged Article</title>
                    <link>https://example.com/tagged</link>
                    <category>Python</category>
                    <category>Programming</category>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        import json

        raw_data = json.loads(result.items[0].raw_json)
        assert "categories" in raw_data

    def test_entry_with_author(self) -> None:
        """Entry with author parses it correctly."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Authored Article</title>
                    <link>https://example.com/authored</link>
                    <author>jane@example.com (Jane Doe)</author>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        import json

        raw_data = json.loads(result.items[0].raw_json)
        assert "author" in raw_data


class TestRssAtomCollectorDateExtraction:
    """Tests for date extraction."""

    def test_published_parsed_date(self) -> None:
        """Uses published_parsed with HIGH confidence."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Dated Article</title>
                    <link>https://example.com/dated</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].published_at is not None
        assert result.items[0].date_confidence.value == "high"

    def test_updated_parsed_date(self) -> None:
        """Uses updated_parsed with MEDIUM confidence when no published."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        # Atom feed with only updated (no published)
        feed = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Updated Article</title>
                <link href="https://example.com/updated"/>
                <updated>2024-01-03T08:00:00Z</updated>
            </entry>
        </feed>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        assert result.items[0].published_at is not None

    def test_no_date_filtered_by_lookback(self) -> None:
        """Items without dates are filtered out by the lookback window."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>No Date Article</title>
                    <link>https://example.com/nodate</link>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        # Items without dates are filtered out by the time-based lookback window
        assert len(result.items) == 0
        assert result.state == SourceState.SOURCE_DONE


class TestRssAtomCollectorMaxItems:
    """Tests for max_items enforcement."""

    def test_max_items_limits_results(self) -> None:
        """max_items limits returned items."""
        collector = RssAtomCollector()
        source_config = make_source_config(max_items=1)
        http_client = MagicMock()

        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Article 1</title>
                    <link>https://example.com/1</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>Article 2</title>
                    <link>https://example.com/2</link>
                    <pubDate>Wed, 03 Jan 2024 10:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>Article 3</title>
                    <link>https://example.com/3</link>
                    <pubDate>Wed, 03 Jan 2024 12:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert len(result.items) == 1
        # Should be the newest article
        assert result.items[0].title == "Article 3"


class TestRssAtomCollectorExceptionHandling:
    """Tests for exception handling."""

    def test_entry_parse_exception_adds_warning(self) -> None:
        """Exception parsing single entry adds warning, continues."""
        collector = RssAtomCollector()
        source_config = make_source_config()
        http_client = MagicMock()

        # Feed with one parseable and one problematic entry
        feed = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Valid Article</title>
                    <link>https://example.com/valid</link>
                    <pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

        http_client.fetch.return_value = make_fetch_result(body=feed)

        result = collector.collect(
            source_config=source_config,
            http_client=http_client,
            now=TEST_TIMESTAMP,
        )

        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 1
