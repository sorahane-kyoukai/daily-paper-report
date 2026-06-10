"""Integration tests for collector framework with SQLite."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.collectors.runner import CollectorRunner
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult
from src.features.store.store import StateStore
from tests.helpers.time import FIXED_NOW


# Sample RSS feed fixture
RSS_FEED_CONTENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>A test feed</description>
    <item>
      <title>Article One</title>
      <link>https://example.com/article-1</link>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
      <description>First article description</description>
    </item>
    <item>
      <title>Article Two</title>
      <link>https://example.com/article-2</link>
      <pubDate>Tue, 02 Jan 2024 12:00:00 GMT</pubDate>
      <description>Second article description</description>
    </item>
    <item>
      <title>Article Three</title>
      <link>https://example.com/article-3</link>
      <pubDate>Wed, 03 Jan 2024 12:00:00 GMT</pubDate>
      <description>Third article description</description>
    </item>
  </channel>
</rss>
"""

# Sample HTML list page fixture
HTML_LIST_CONTENT = b"""<!DOCTYPE html>
<html>
<head><title>Blog</title></head>
<body>
  <main>
    <article>
      <h2><a href="/post/1">First Post</a></h2>
      <time datetime="2024-01-15T10:00:00Z">January 15, 2024</time>
      <p class="excerpt">This is the first post</p>
    </article>
    <article>
      <h2><a href="/post/2">Second Post</a></h2>
      <time datetime="2024-01-16T10:00:00Z">January 16, 2024</time>
      <p class="excerpt">This is the second post</p>
    </article>
  </main>
</body>
</html>
"""


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_state.db"


@pytest.fixture
def store(temp_db: Path) -> Generator[StateStore]:
    """Create and connect a state store."""
    store = StateStore(temp_db, run_id="test-run-001")
    store.connect()
    yield store
    store.close()


@pytest.fixture
def mock_http_client(store: StateStore) -> MagicMock:  # noqa: ARG001
    """Create a mock HTTP client."""
    return MagicMock(spec=HttpFetcher)


@pytest.fixture
def rss_source() -> SourceConfig:
    """Create an RSS source configuration."""
    return SourceConfig(
        id="test-rss",
        name="Test RSS Feed",
        url="https://example.com/feed.rss",
        tier=SourceTier.TIER_0,
        method=SourceMethod.RSS_ATOM,
        kind=SourceKind.BLOG,
        max_items=100,
    )


@pytest.fixture
def html_source() -> SourceConfig:
    """Create an HTML list source configuration."""
    return SourceConfig(
        id="test-html",
        name="Test HTML Blog",
        url="https://example.com/blog",
        tier=SourceTier.TIER_1,
        method=SourceMethod.HTML_LIST,
        kind=SourceKind.BLOG,
        max_items=100,
    )


class TestCollectorRunnerIntegration:
    """Integration tests for CollectorRunner with SQLite."""

    def test_rss_collector_upserts_items(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
    ) -> None:
        """RSS collector upserts items to SQLite."""
        # Configure mock to return RSS feed
        mock_http_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=rss_source.url,
            headers={},
            body_bytes=RSS_FEED_CONTENT,
            cache_hit=False,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([rss_source], now=FIXED_NOW)

        # Verify runner result
        assert result.sources_succeeded == 1
        assert result.sources_failed == 0
        assert result.total_items == 3

        # Verify items in database
        stats = store.get_stats()
        assert stats["items"] == 3

        # Verify item details
        item = store.get_item("https://example.com/article-1")
        assert item is not None
        assert item.title == "Article One"
        assert item.source_id == "test-rss"

    def test_html_collector_upserts_items(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        html_source: SourceConfig,
    ) -> None:
        """HTML list collector upserts items to SQLite."""
        # Configure mock to return HTML
        mock_http_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=html_source.url,
            headers={"content-type": "text/html; charset=utf-8"},
            body_bytes=HTML_LIST_CONTENT,
            cache_hit=False,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([html_source], now=FIXED_NOW)

        # Verify runner result
        assert result.sources_succeeded == 1
        assert result.total_items == 2

        # Verify items in database
        stats = store.get_stats()
        assert stats["items"] == 2

    def test_multiple_collectors_sequential(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
        html_source: SourceConfig,
    ) -> None:
        """Multiple collectors run and upsert items.

        Note: Uses max_workers=1 because SQLite connections cannot be shared
        across threads. In production, thread-local connections would be used.
        """

        # Configure mock to return appropriate content
        def mock_fetch(source_id: str, url: str, **kwargs: object) -> FetchResult:
            if "rss" in source_id:
                return FetchResult(
                    status_code=200,
                    final_url=url,
                    headers={},
                    body_bytes=RSS_FEED_CONTENT,
                    cache_hit=False,
                    error=None,
                )
            return FetchResult(
                status_code=200,
                final_url=url,
                headers={"content-type": "text/html; charset=utf-8"},
                body_bytes=HTML_LIST_CONTENT,
                cache_hit=False,
                error=None,
            )

        mock_http_client.fetch.side_effect = mock_fetch

        # Use max_workers=1 due to SQLite thread safety constraints in tests
        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([rss_source, html_source], now=FIXED_NOW)

        # Verify both sources succeeded
        assert result.sources_succeeded == 2
        assert result.sources_failed == 0
        assert result.total_items == 5  # 3 from RSS + 2 from HTML

        # Verify all items in database
        stats = store.get_stats()
        assert stats["items"] == 5

    def test_failing_source_isolated(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
        html_source: SourceConfig,
    ) -> None:
        """A failing source doesn't prevent other sources from succeeding."""

        # Configure mock: RSS fails, HTML succeeds
        def mock_fetch(source_id: str, url: str, **kwargs: object) -> FetchResult:
            if "rss" in source_id:
                return FetchResult(
                    status_code=500,
                    final_url=url,
                    headers={},
                    body_bytes=b"",
                    cache_hit=False,
                    error=FetchError(
                        error_class=FetchErrorClass.HTTP_5XX,
                        message="Server error",
                        status_code=500,
                    ),
                )
            return FetchResult(
                status_code=200,
                final_url=url,
                headers={"content-type": "text/html; charset=utf-8"},
                body_bytes=HTML_LIST_CONTENT,
                cache_hit=False,
                error=None,
            )

        mock_http_client.fetch.side_effect = mock_fetch

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([rss_source, html_source], now=FIXED_NOW)

        # Verify isolation
        assert result.sources_succeeded == 1
        assert result.sources_failed == 1
        assert result.total_items == 2  # Only from HTML

        # Verify HTML items persisted
        stats = store.get_stats()
        assert stats["items"] == 2

        # Verify source results
        assert result.source_results["test-rss"].result.success is False
        assert result.source_results["test-html"].result.success is True

    def test_idempotent_upsert(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
    ) -> None:
        """Running same collector twice doesn't duplicate items."""
        mock_http_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=rss_source.url,
            headers={},
            body_bytes=RSS_FEED_CONTENT,
            cache_hit=False,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        # First run
        result1 = runner.run([rss_source], now=FIXED_NOW)
        assert result1.total_new == 3
        assert result1.total_updated == 0

        # Second run with same content
        result2 = runner.run([rss_source], now=FIXED_NOW)
        assert result2.total_new == 0  # No new items
        assert result2.total_items == 3  # Same items seen

        # Verify still only 3 items in DB
        stats = store.get_stats()
        assert stats["items"] == 3

    def test_deterministic_ordering(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
    ) -> None:
        """Items are returned in deterministic order."""
        mock_http_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=rss_source.url,
            headers={},
            body_bytes=RSS_FEED_CONTENT,
            cache_hit=False,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([rss_source], now=FIXED_NOW)

        # Verify items are sorted by date descending
        source_result = result.source_results["test-rss"]
        items = source_result.result.items
        assert len(items) == 3

        # Article Three (Jan 3) should be first
        assert items[0].title == "Article Three"
        # Article Two (Jan 2) should be second
        assert items[1].title == "Article Two"
        # Article One (Jan 1) should be last
        assert items[2].title == "Article One"

    def test_max_items_enforced(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
    ) -> None:
        """max_items_per_source is enforced."""
        # Create source with max_items=1
        source = SourceConfig(
            id="test-limited",
            name="Limited Source",
            url="https://example.com/feed.rss",
            tier=SourceTier.TIER_0,
            method=SourceMethod.RSS_ATOM,
            kind=SourceKind.BLOG,
            max_items=1,
        )

        mock_http_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=source.url,
            headers={},
            body_bytes=RSS_FEED_CONTENT,
            cache_hit=False,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([source], now=FIXED_NOW)

        # Only 1 item should be collected
        assert result.total_items == 1
        stats = store.get_stats()
        assert stats["items"] == 1

    def test_state_machine_transitions(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
    ) -> None:
        """State machine transitions are recorded correctly."""
        mock_http_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url=rss_source.url,
            headers={},
            body_bytes=RSS_FEED_CONTENT,
            cache_hit=False,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([rss_source], now=FIXED_NOW)

        # Verify final state
        source_result = result.source_results["test-rss"]
        assert source_result.result.state == SourceState.SOURCE_DONE

    def test_cache_hit_no_items(
        self,
        store: StateStore,
        mock_http_client: MagicMock,
        rss_source: SourceConfig,
    ) -> None:
        """Cache hit (304) returns empty items without error."""
        mock_http_client.fetch.return_value = FetchResult(
            status_code=304,
            final_url=rss_source.url,
            headers={},
            body_bytes=b"",
            cache_hit=True,
            error=None,
        )

        runner = CollectorRunner(
            store=store,
            http_client=mock_http_client,
            run_id="test-run-001",
            max_workers=1,
        )

        result = runner.run([rss_source], now=FIXED_NOW)

        # Should succeed with 0 items
        assert result.sources_succeeded == 1
        assert result.total_items == 0
        source_result = result.source_results["test-rss"]
        assert source_result.result.success is True
