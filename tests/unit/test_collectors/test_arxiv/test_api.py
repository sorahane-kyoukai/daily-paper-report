"""Unit tests for arXiv API collector."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from src.collectors.arxiv.api import (
    ArxivApiCollector,
    ArxivApiConfig,
    ArxivApiRateLimiter,
)
from src.collectors.arxiv.metrics import ArxivMetrics
from src.collectors.state_machine import SourceState
from src.features.config.schemas.sources import SourceConfig, SourceKind, SourceMethod
from src.features.fetch.client import HttpFetcher
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult


class MockRateLimiter:
    """Mock rate limiter for testing without actual delays."""

    def __init__(self) -> None:
        self.wait_calls = 0
        self.rate_limited_calls = 0
        self.retry_after_values: list[float | None] = []

    def wait_if_needed(self) -> None:
        """No-op implementation for tests."""
        self.wait_calls += 1

    def notify_rate_limited(self, retry_after: float | None = None) -> None:
        """No-op implementation for tests."""
        self.rate_limited_calls += 1
        self.retry_after_values.append(retry_after)


# Sample arXiv API Atom response
# Note: Published dates are set within a few hours of each other so both
# items pass the 24-hour lookback filter when using the matching run_timestamp.
SAMPLE_API_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title type="html">ArXiv Query: DeepSeek</title>
  <id>http://arxiv.org/api/query</id>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>DeepSeek: A Large Language Model</title>
    <summary>This paper presents DeepSeek, a large language model...</summary>
    <author><name>Test Author</name></author>
    <published>2024-01-15T10:00:00Z</published>
    <updated>2024-01-15T12:00:00Z</updated>
    <arxiv:primary_category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.12346v2</id>
    <title>DeepSeek-Coder: A Code Model</title>
    <summary>This paper presents DeepSeek-Coder...</summary>
    <author><name>Another Author</name></author>
    <published>2024-01-15T08:00:00Z</published>
    <updated>2024-01-15T10:00:00Z</updated>
    <arxiv:primary_category term="cs.SE" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.SE" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2401.12346v2" rel="alternate" type="text/html"/>
  </entry>
</feed>"""


EMPTY_API_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title type="html">ArXiv Query</title>
  <id>http://arxiv.org/api/query</id>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:totalResults>
</feed>"""


def build_api_response(
    entries: list[dict[str, str]],
    total_results: int | None = None,
) -> bytes:
    """Build a minimal Atom API response for pagination tests."""
    entry_xml = [
        (
            f"""  <entry>
    <id>http://arxiv.org/abs/{entry["id"]}</id>
    <title>{entry["title"]}</title>
    <summary>{entry["summary"]}</summary>
    <author><name>{entry["author"]}</name></author>
    <published>{entry["published"]}</published>
    <updated>{entry["updated"]}</updated>
    <arxiv:primary_category term="{entry["category"]}" scheme="http://arxiv.org/schemas/atom"/>
    <category term="{entry["category"]}" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/{entry["id"]}" rel="alternate" type="text/html"/>
  </entry>"""
        )
        for entry in entries
    ]

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title type="html">ArXiv Query</title>
  <id>http://arxiv.org/api/query</id>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">{count}</opensearch:totalResults>
{entries}
</feed>""".format(
        count=total_results if total_results is not None else len(entries),
        entries="\n".join(entry_xml),
    )
    return xml.encode()


def make_source_config(
    source_id: str = "arxiv-cn-models",
    query: str = 'ti:"DeepSeek"',
    max_results: int = 50,
) -> SourceConfig:
    """Create a test source configuration for API queries."""
    return SourceConfig(
        id=source_id,
        name="arXiv CN Models",
        url="http://export.arxiv.org/api/query",  # API base URL
        method=SourceMethod.RSS_ATOM,  # Placeholder
        tier=0,
        kind=SourceKind.PAPER,
        max_items=max_results,
        query=query,
    )


class TestArxivApiConfig:
    """Tests for ArxivApiConfig class."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ArxivApiConfig(query='ti:"test"')
        assert config.max_results == 50
        assert config.sort_by == "submittedDate"
        assert config.sort_order == "descending"

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = ArxivApiConfig(
            query='ti:"test"',
            max_results=100,
            sort_by="relevance",
            sort_order="ascending",
        )
        assert config.max_results == 100
        assert config.sort_by == "relevance"
        assert config.sort_order == "ascending"


class TestArxivApiRateLimiter:
    """Tests for ArxivApiRateLimiter class."""

    def test_first_call_no_wait(self) -> None:
        """Test that first call doesn't wait (with warmup disabled)."""
        limiter = ArxivApiRateLimiter(min_interval=1.0, warmup_seconds=0.0)
        import time

        start = time.monotonic()
        limiter.wait_if_needed()
        elapsed = time.monotonic() - start

        assert elapsed < 0.1  # Should be nearly instant

    def test_rapid_calls_wait(self) -> None:
        """Test that rapid calls are rate limited."""
        limiter = ArxivApiRateLimiter(min_interval=0.1, warmup_seconds=0.0)
        import time

        limiter.wait_if_needed()
        start = time.monotonic()
        limiter.wait_if_needed()
        elapsed = time.monotonic() - start

        # Should wait close to the interval
        assert elapsed >= 0.08

    def test_concurrent_calls_are_serialized(self) -> None:
        """Concurrent callers should not bypass the shared rate limiter."""
        import time
        from concurrent.futures import ThreadPoolExecutor

        limiter = ArxivApiRateLimiter(
            min_interval=0.02,
            max_requests_per_window=100,
            warmup_seconds=0.0,
        )

        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: limiter.wait_if_needed(), range(4)))
        elapsed = time.monotonic() - start

        assert elapsed >= 0.05


class TestArxivApiCollector:
    """Tests for ArxivApiCollector class."""

    def setup_method(self) -> None:
        """Reset metrics before each test."""
        ArxivMetrics.reset()
        self._sleep_patcher = patch.object(
            ArxivApiCollector,
            "_sleep_before_retry",
            lambda _collector, _seconds: None,
        )
        self._sleep_patcher.start()

    def teardown_method(self) -> None:
        """Restore patched retry sleep."""
        self._sleep_patcher.stop()

    def test_successful_collection(self) -> None:
        """Test successful API query collection."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=SAMPLE_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        # Use a timestamp close to the sample data dates (2024-01-15/16)
        # so items aren't filtered out by the 24-hour lookback window
        run_timestamp = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
        result = collector.collect(source_config, mock_client, run_timestamp)

        assert result.success
        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 2

    def test_canonical_url_format(self) -> None:
        """Test that URLs are normalized to canonical format."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=SAMPLE_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        # Use a timestamp close to the sample data dates
        run_timestamp = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
        result = collector.collect(source_config, mock_client, run_timestamp)

        for item in result.items:
            assert item.url.startswith("https://arxiv.org/abs/")
            # Should not contain version suffix
            assert "v1" not in item.url
            assert "v2" not in item.url

    def test_empty_response_success(self) -> None:
        """Test that empty response returns success."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=EMPTY_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        result = collector.collect(source_config, mock_client, datetime.now(UTC))

        assert result.success
        assert len(result.items) == 0

    def test_keyword_query_long_lookback_uses_limited_page_budget(self) -> None:
        """Broad keyword queries use a bounded page budget during backfills."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config(query='ti:"DeepSeek"', max_results=2)

        mock_client = MagicMock(spec=HttpFetcher)
        body = build_api_response(
            [
                {
                    "id": "2401.30001v1",
                    "title": "Keyword Page 1",
                    "summary": "summary",
                    "author": "Author 1",
                    "published": "2024-01-16T11:00:00Z",
                    "updated": "2024-01-16T11:10:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.30002v1",
                    "title": "Keyword Page 2",
                    "summary": "summary",
                    "author": "Author 2",
                    "published": "2024-01-16T10:00:00Z",
                    "updated": "2024-01-16T10:10:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=4,
        )
        mock_client.fetch.side_effect = [
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=body,
                cache_hit=False,
                error=None,
            )
            for _ in range(6)
        ]

        result = collector.collect(
            source_config,
            mock_client,
            datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC),
            lookback_hours=168,
            max_items_override=0,
        )

        assert result.success
        assert mock_client.fetch.call_count == 2

    def test_keyword_query_long_lookback_keeps_first_page_on_later_fetch_error(
        self,
    ) -> None:
        """Keyword backfills should keep first-page results if a later page fails."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config(query='ti:"DeepSeek"', max_results=2)

        mock_client = MagicMock(spec=HttpFetcher)
        body = build_api_response(
            [
                {
                    "id": "2401.31001v1",
                    "title": "Keyword Page 1",
                    "summary": "summary",
                    "author": "Author 1",
                    "published": "2024-01-16T11:00:00Z",
                    "updated": "2024-01-16T11:10:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.31002v1",
                    "title": "Keyword Page 2",
                    "summary": "summary",
                    "author": "Author 2",
                    "published": "2024-01-16T10:00:00Z",
                    "updated": "2024-01-16T10:10:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=4,
        )
        mock_client.fetch.side_effect = [
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=body,
                cache_hit=False,
                error=None,
            ),
            RuntimeError("HTTP 429"),
        ]

        result = collector.collect(
            source_config,
            mock_client,
            datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC),
            lookback_hours=168,
            max_items_override=0,
        )

        assert result.success
        assert len(result.items) == 2

    def test_fetch_error_returns_failed(self) -> None:
        """Test that fetch error returns failed state."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=503,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=b"",
            cache_hit=False,
            error=FetchError(
                error_class=FetchErrorClass.HTTP_5XX,
                message="Service unavailable",
                status_code=503,
            ),
        )

        result = collector.collect(source_config, mock_client, datetime.now(UTC))

        assert not result.success
        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None

    def test_rate_limit_retries_with_arxiv_cooldown_not_fetcher_retry(self) -> None:
        """429 should be retried by arXiv cooldown logic, not HttpFetcher retries."""
        rate_limiter = MockRateLimiter()
        collector = ArxivApiCollector(run_id="test", rate_limiter=rate_limiter)
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.side_effect = [
            FetchResult(
                status_code=429,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=b"",
                cache_hit=False,
                error=FetchError(
                    error_class=FetchErrorClass.RATE_LIMITED,
                    message="Too Many Requests",
                    status_code=429,
                    retry_after=7,
                ),
            ),
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=EMPTY_API_RESPONSE,
                cache_hit=False,
                error=None,
            ),
        ]

        result = collector.collect(source_config, mock_client, datetime.now(UTC))

        assert result.success
        assert mock_client.fetch.call_count == 2
        assert rate_limiter.rate_limited_calls == 1
        assert rate_limiter.retry_after_values == [7.0]
        assert all(
            call.kwargs["max_retries"] == 0 for call in mock_client.fetch.call_args_list
        )

    def test_rate_limit_exhaustion_fails_daily_query(self) -> None:
        """A daily arXiv query fails rather than silently publishing partial coverage."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=429,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=b"",
            cache_hit=False,
            error=FetchError(
                error_class=FetchErrorClass.RATE_LIMITED,
                message="Too Many Requests",
                status_code=429,
            ),
        )

        result = collector.collect(source_config, mock_client, datetime.now(UTC))

        assert not result.success
        assert result.state == SourceState.SOURCE_FAILED
        assert mock_client.fetch.call_count == 5

    def test_malformed_xml_handled(self) -> None:
        """Test that malformed XML is handled gracefully."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=b"<invalid xml",
            cache_hit=False,
            error=None,
        )

        result = collector.collect(source_config, mock_client, datetime.now(UTC))

        # Malformed API responses must fail so coverage gaps are visible.
        assert not result.success
        assert len(result.items) == 0
        assert len(result.parse_warnings) > 0

    def test_metrics_recorded(self) -> None:
        """Test that metrics are recorded."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=SAMPLE_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        # Use a timestamp close to the sample data dates
        run_timestamp = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
        collector.collect(source_config, mock_client, run_timestamp)

        metrics = ArxivMetrics.get_instance()
        assert metrics.get_items_total("api") == 2
        assert metrics.get_api_latency_stats()["count"] == 1.0

    def test_unlimited_override_paginates_until_cutoff(self) -> None:
        """An unlimited override should fetch every page needed for the window."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config(max_results=2)

        page_1 = build_api_response(
            [
                {
                    "id": "2401.20001v1",
                    "title": "Page 1 / Newest 1",
                    "summary": "summary",
                    "author": "Author 1",
                    "published": "2024-01-16T11:00:00Z",
                    "updated": "2024-01-16T11:10:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.20002v1",
                    "title": "Page 1 / Newest 2",
                    "summary": "summary",
                    "author": "Author 2",
                    "published": "2024-01-16T10:00:00Z",
                    "updated": "2024-01-16T10:10:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=6,
        )
        page_2 = build_api_response(
            [
                {
                    "id": "2401.20003v1",
                    "title": "Page 2 / Mid 1",
                    "summary": "summary",
                    "author": "Author 3",
                    "published": "2024-01-15T14:00:00Z",
                    "updated": "2024-01-15T14:10:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.20004v1",
                    "title": "Page 2 / Mid 2",
                    "summary": "summary",
                    "author": "Author 4",
                    "published": "2024-01-15T13:00:00Z",
                    "updated": "2024-01-15T13:10:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=6,
        )
        page_3 = build_api_response(
            [
                {
                    "id": "2401.20005v1",
                    "title": "Page 3 / Boundary",
                    "summary": "summary",
                    "author": "Author 5",
                    "published": "2024-01-15T12:30:00Z",
                    "updated": "2024-01-15T12:40:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.20006v1",
                    "title": "Page 3 / Older",
                    "summary": "summary",
                    "author": "Author 6",
                    "published": "2024-01-15T11:30:00Z",
                    "updated": "2024-01-15T11:40:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=6,
        )

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.side_effect = [
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=page_1,
                cache_hit=False,
                error=None,
            ),
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=page_2,
                cache_hit=False,
                error=None,
            ),
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=page_3,
                cache_hit=False,
                error=None,
            ),
        ]

        run_timestamp = datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC)
        result = collector.collect(
            source_config,
            mock_client,
            run_timestamp,
            max_items_override=0,
        )

        assert result.success
        assert len(result.items) == 5

        starts = []
        for call in mock_client.fetch.call_args_list:
            parsed = urlparse(call.kwargs["url"])
            starts.append(parse_qs(parsed.query)["start"][0])
        assert starts == ["0", "2", "4"]

    def test_query_is_bounded_to_submitted_date_window(self) -> None:
        """The collector should bound arXiv queries to the requested time window."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config(query="cat:cs.AI", max_results=2)

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=EMPTY_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        run_timestamp = datetime(2024, 1, 16, 12, 34, 56, tzinfo=UTC)
        collector.collect(source_config, mock_client, run_timestamp)

        parsed = urlparse(mock_client.fetch.call_args.kwargs["url"])
        search_query = parse_qs(parsed.query)["search_query"][0]
        assert search_query == (
            "(cat:cs.AI) AND submittedDate:[202401151234 TO 202401161234]"
        )

    def test_pagination_continues_past_older_published_entries(self) -> None:
        """Stop conditions must follow API page bounds, not entry published_at order."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config(query="cat:cs.AI", max_results=2)

        page_1 = build_api_response(
            [
                {
                    "id": "2401.40001v1",
                    "title": "Newest 1",
                    "summary": "summary",
                    "author": "Author 1",
                    "published": "2024-01-16T11:00:00Z",
                    "updated": "2024-01-16T11:05:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.40002v1",
                    "title": "Newest 2",
                    "summary": "summary",
                    "author": "Author 2",
                    "published": "2024-01-16T10:00:00Z",
                    "updated": "2024-01-16T10:05:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=5,
        )
        page_2 = build_api_response(
            [
                {
                    "id": "2401.40003v1",
                    "title": "In window but later page",
                    "summary": "summary",
                    "author": "Author 3",
                    "published": "2024-01-15T14:00:00Z",
                    "updated": "2024-01-16T09:05:00Z",
                    "category": "cs.AI",
                },
                {
                    "id": "2401.40004v1",
                    "title": "Older published but recent submit",
                    "summary": "summary",
                    "author": "Author 4",
                    "published": "2024-01-15T11:00:00Z",
                    "updated": "2024-01-16T09:00:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=5,
        )
        page_3 = build_api_response(
            [
                {
                    "id": "2401.40005v1",
                    "title": "Should still be fetched",
                    "summary": "summary",
                    "author": "Author 5",
                    "published": "2024-01-15T13:00:00Z",
                    "updated": "2024-01-16T08:55:00Z",
                    "category": "cs.AI",
                },
            ],
            total_results=5,
        )

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.side_effect = [
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=page_1,
                cache_hit=False,
                error=None,
            ),
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=page_2,
                cache_hit=False,
                error=None,
            ),
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=page_3,
                cache_hit=False,
                error=None,
            ),
        ]

        run_timestamp = datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC)
        result = collector.collect(
            source_config,
            mock_client,
            run_timestamp,
            max_items_override=0,
        )

        assert result.success
        assert len(result.items) == 4

        starts = []
        for call in mock_client.fetch.call_args_list:
            parsed = urlparse(call.kwargs["url"])
            starts.append(parse_qs(parsed.query)["start"][0])
        assert starts == ["0", "2", "4"]

    def test_positive_override_still_enforces_final_cap(self) -> None:
        """A positive override should still cap the final result set."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config(max_results=2)

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.side_effect = [
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=SAMPLE_API_RESPONSE,
                cache_hit=False,
                error=None,
            ),
            FetchResult(
                status_code=200,
                final_url="http://export.arxiv.org/api/query",
                headers={},
                body_bytes=EMPTY_API_RESPONSE,
                cache_hit=False,
                error=None,
            ),
        ]

        run_timestamp = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
        result = collector.collect(
            source_config,
            mock_client,
            run_timestamp,
            max_items_override=1,
        )

        assert result.success
        assert len(result.items) == 1

    def test_categories_extracted(self) -> None:
        """Test that categories are extracted from entries."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=SAMPLE_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        # Use a timestamp close to the sample data dates
        run_timestamp = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
        result = collector.collect(source_config, mock_client, run_timestamp)

        import json

        # First item should have cs.CL and cs.AI categories
        raw = json.loads(result.items[0].raw_json)
        assert "categories" in raw
        assert "cs.CL" in raw["categories"]

    def test_date_extraction_high_confidence(self) -> None:
        """Test that published date gives high confidence."""
        collector = ArxivApiCollector(run_id="test", rate_limiter=MockRateLimiter())
        source_config = make_source_config()

        mock_client = MagicMock(spec=HttpFetcher)
        mock_client.fetch.return_value = FetchResult(
            status_code=200,
            final_url="http://export.arxiv.org/api/query",
            headers={},
            body_bytes=SAMPLE_API_RESPONSE,
            cache_hit=False,
            error=None,
        )

        # Use a timestamp close to the sample data dates
        run_timestamp = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
        result = collector.collect(source_config, mock_client, run_timestamp)

        assert result.items[0].published_at is not None
        from src.features.store.models import DateConfidence

        assert result.items[0].date_confidence == DateConfidence.HIGH
