"""Integration tests for HTTP conditional requests with ETag/Last-Modified."""

import tempfile
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.features.fetch.client import HttpFetcher
from src.features.fetch.config import FetchConfig
from src.features.fetch.metrics import FetchMetrics
from src.features.fetch.models import RetryPolicy
from src.features.store.metrics import StoreMetrics
from src.features.store.store import StateStore


def get_server_url(server: HTTPServer, path: str = "/resource") -> str:
    """Get the URL for a test server.

    Args:
        server: The HTTP server instance.
        path: The URL path.

    Returns:
        Complete URL for the server.
    """
    host, port = server.server_address[0], server.server_address[1]
    # Ensure host is a string (may be bytes in some socket scenarios)
    if isinstance(host, bytes):
        host = host.decode("utf-8")
    return f"http://{host}:{port}{path}"


class CachingHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler that supports ETag and Last-Modified caching."""

    # Class-level state for test responses
    response_body: bytes = b'{"data": "test content for caching"}'
    etag: str = '"abc123"'
    last_modified: str = "Mon, 01 Jan 2024 00:00:00 GMT"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress log messages during tests."""

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests with conditional caching support."""
        # Check for conditional request headers
        if_none_match = self.headers.get("If-None-Match")
        if_modified_since = self.headers.get("If-Modified-Since")

        # If client has current version, return 304
        if if_none_match == self.etag or if_modified_since == self.last_modified:
            self.send_response(304)
            self.send_header("ETag", self.etag)
            self.send_header("Last-Modified", self.last_modified)
            self.end_headers()
            return

        # Return full response with cache headers
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.response_body)))
        self.send_header("ETag", self.etag)
        self.send_header("Last-Modified", self.last_modified)
        self.end_headers()
        self.wfile.write(self.response_body)


class Error5xxHandler(BaseHTTPRequestHandler):
    """HTTP handler that returns 5xx errors for retry testing."""

    request_count: int = 0
    error_count: int = 3  # Return error for first N requests

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress log messages during tests."""

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests, returning 503 for first N requests."""
        Error5xxHandler.request_count += 1

        if Error5xxHandler.request_count <= Error5xxHandler.error_count:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Service Unavailable")
            return

        # After error_count, return success
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


class RateLimitHandler(BaseHTTPRequestHandler):
    """HTTP handler that returns 429 with Retry-After."""

    request_count: int = 0

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress log messages during tests."""

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests, returning 429 on first request."""
        RateLimitHandler.request_count += 1

        if RateLimitHandler.request_count == 1:
            self.send_response(429)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Retry-After", "1")  # 1 second
            self.end_headers()
            self.wfile.write(b"Too Many Requests")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


@pytest.fixture
def temp_db_path() -> Generator[Path]:
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_state.sqlite"


@pytest.fixture
def store(temp_db_path: Path) -> Generator[StateStore]:
    """Create a connected state store."""
    StoreMetrics.reset()
    store = StateStore(temp_db_path, run_id="test-run-001")
    store.connect()
    yield store
    store.close()


@pytest.fixture
def caching_server() -> Generator[HTTPServer]:
    """Start a local HTTP server with caching support."""
    server = HTTPServer(("127.0.0.1", 0), CachingHTTPHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture
def error_server() -> Generator[HTTPServer]:
    """Start a local HTTP server that returns 5xx errors."""
    Error5xxHandler.request_count = 0
    Error5xxHandler.error_count = 2
    server = HTTPServer(("127.0.0.1", 0), Error5xxHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture
def rate_limit_server() -> Generator[HTTPServer]:
    """Start a local HTTP server that returns 429."""
    RateLimitHandler.request_count = 0
    server = HTTPServer(("127.0.0.1", 0), RateLimitHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    server.shutdown()


class TestConditionalRequests:
    """Integration tests for ETag/Last-Modified conditional requests."""

    def test_first_fetch_stores_cache_headers(
        self,
        store: StateStore,
        caching_server: HTTPServer,
    ) -> None:
        """Test that first fetch stores ETag and Last-Modified."""
        FetchMetrics.reset()
        url = get_server_url(caching_server)

        config = FetchConfig(retry_policy=RetryPolicy(max_retries=0))
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        result = fetcher.fetch(source_id="test-source", url=url)

        assert result.status_code == 200
        assert result.cache_hit is False
        assert result.body_size > 0

        # Check cache was stored
        cache = store.get_http_cache("test-source")
        assert cache is not None
        assert cache.etag == '"abc123"'
        assert cache.last_modified == "Mon, 01 Jan 2024 00:00:00 GMT"
        assert cache.last_status == 200

    def test_second_fetch_gets_304(
        self,
        store: StateStore,
        caching_server: HTTPServer,
    ) -> None:
        """Test that second fetch receives 304 Not Modified."""
        FetchMetrics.reset()
        url = get_server_url(caching_server)

        config = FetchConfig(retry_policy=RetryPolicy(max_retries=0))
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        # First fetch
        result1 = fetcher.fetch(source_id="test-source", url=url)
        assert result1.status_code == 200
        assert result1.cache_hit is False
        first_bytes = result1.body_size

        # Second fetch
        result2 = fetcher.fetch(source_id="test-source", url=url)
        assert result2.status_code == 304
        assert result2.cache_hit is True
        second_bytes = result2.body_size

        # Verify payload reduction
        assert first_bytes > 0
        assert second_bytes == 0  # 304 has no body

    def test_cache_hit_metrics_recorded(
        self,
        store: StateStore,
        caching_server: HTTPServer,
    ) -> None:
        """Test that cache hit metrics are recorded."""
        FetchMetrics.reset()
        url = get_server_url(caching_server)

        config = FetchConfig(retry_policy=RetryPolicy(max_retries=0))
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        # First fetch
        fetcher.fetch(source_id="test-source", url=url)

        # Second fetch
        fetcher.fetch(source_id="test-source", url=url)

        metrics = FetchMetrics.get_instance()
        assert metrics.http_cache_hits_total == 1

    def test_payload_reduction_80_percent(
        self,
        store: StateStore,
        caching_server: HTTPServer,
    ) -> None:
        """Test that conditional requests reduce payload by at least 80%."""
        FetchMetrics.reset()
        url = get_server_url(caching_server)

        config = FetchConfig(retry_policy=RetryPolicy(max_retries=0))
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        # First fetch - get full response
        result1 = fetcher.fetch(source_id="test-source", url=url)
        first_bytes = result1.body_size

        # Second fetch - should be 304 with no body
        result2 = fetcher.fetch(source_id="test-source", url=url)
        second_bytes = result2.body_size

        # Calculate reduction
        if first_bytes > 0:
            reduction = (first_bytes - second_bytes) / first_bytes * 100
            assert reduction >= 80, f"Payload reduction was only {reduction}%"


class TestRetryBehavior:
    """Integration tests for retry behavior with 5xx errors."""

    def test_5xx_retried_and_succeeds(
        self,
        store: StateStore,
        error_server: HTTPServer,
    ) -> None:
        """Test that 5xx errors are retried and eventually succeed."""
        FetchMetrics.reset()
        url = get_server_url(error_server)

        config = FetchConfig(
            retry_policy=RetryPolicy(
                max_retries=3,
                base_delay_ms=10,  # Short delay for test
            )
        )
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        result = fetcher.fetch(source_id="test-source", url=url)

        # Should succeed after retries
        assert result.status_code == 200
        assert result.error is None

        # Verify retries happened
        metrics = FetchMetrics.get_instance()
        assert metrics.http_retry_total >= 1

    def test_5xx_exhausts_retries(
        self,
        store: StateStore,
        error_server: HTTPServer,
    ) -> None:
        """Test that 5xx errors fail after max retries."""
        FetchMetrics.reset()
        Error5xxHandler.request_count = 0
        Error5xxHandler.error_count = 10  # More than max_retries

        url = get_server_url(error_server)

        config = FetchConfig(
            retry_policy=RetryPolicy(
                max_retries=2,
                base_delay_ms=10,
            )
        )
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        result = fetcher.fetch(source_id="test-source", url=url)

        # Should fail
        assert result.error is not None
        assert result.error.error_class.value in ["HTTP_5XX", "CONNECTION_ERROR"]

        # Verify attempt count: 1 initial + 2 retries = 3 total
        assert Error5xxHandler.request_count == 3


class TestRateLimitHandling:
    """Integration tests for 429 rate limit handling."""

    def test_429_retried_with_retry_after(
        self,
        store: StateStore,
        rate_limit_server: HTTPServer,
    ) -> None:
        """Test that 429 errors are retried after Retry-After delay."""
        FetchMetrics.reset()
        url = get_server_url(rate_limit_server)

        config = FetchConfig(
            retry_policy=RetryPolicy(
                max_retries=3,
                base_delay_ms=10,
            )
        )
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        result = fetcher.fetch(source_id="test-source", url=url)

        # Should succeed after retry
        assert result.status_code == 200
        assert result.error is None

        # Verify requests: 1 (429) + 1 (200) = 2
        assert RateLimitHandler.request_count == 2


class TestFailureIsolation:
    """Integration tests for failure isolation between sources."""

    def test_one_source_failure_does_not_block_others(
        self,
        store: StateStore,
        caching_server: HTTPServer,
        error_server: HTTPServer,
    ) -> None:
        """Test that failure in one source doesn't abort others."""
        FetchMetrics.reset()
        Error5xxHandler.request_count = 0
        Error5xxHandler.error_count = 100  # Always fail

        good_url = get_server_url(caching_server)
        bad_url = get_server_url(error_server)

        config = FetchConfig(
            retry_policy=RetryPolicy(
                max_retries=1,
                base_delay_ms=10,
            ),
            fail_fast=False,  # Default, but explicit
        )
        fetcher = HttpFetcher(config=config, store=store, run_id="test-run")

        # Fetch from failing source
        result_bad = fetcher.fetch(source_id="bad-source", url=bad_url)

        # Fetch from good source (should still work)
        result_good = fetcher.fetch(source_id="good-source", url=good_url)

        # Bad source failed
        assert result_bad.error is not None

        # Good source succeeded
        assert result_good.status_code == 200
        assert result_good.error is None
