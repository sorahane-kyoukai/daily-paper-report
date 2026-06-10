"""Mock HTTP transport for E2E testing with network blocking.

Provides a mock HTTP client that:
- Returns fixture-backed responses for registered URLs
- Blocks all outbound network access
- Records all request attempts for audit
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from src.e2e.fixtures import FixtureInfo, FixtureLoader
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult


logger = structlog.get_logger()


class NetworkAccessBlockedError(Exception):
    """Raised when a request attempts outbound network access."""

    def __init__(self, url: str) -> None:
        """Initialize the error.

        Args:
            url: URL that was blocked.
        """
        self.url = url
        super().__init__(
            f"Network access blocked: {url}. "
            "E2E harness runs with fixture-backed responses only."
        )


@dataclass
class RequestRecord:
    """Record of an HTTP request attempt.

    Attributes:
        url: Requested URL.
        timestamp: When request was made.
        source_id: Source ID if provided.
        fixture_name: Fixture name if matched.
        blocked: Whether request was blocked.
    """

    url: str
    timestamp: datetime
    source_id: str | None = None
    fixture_name: str | None = None
    blocked: bool = False


@dataclass
class MockTransportStats:
    """Statistics for mock transport usage.

    Attributes:
        requests_total: Total requests made.
        requests_matched: Requests matched to fixtures.
        requests_blocked: Requests blocked (no fixture).
    """

    requests_total: int = 0
    requests_matched: int = 0
    requests_blocked: int = 0
    request_log: list[RequestRecord] = field(default_factory=list)


class MockHttpClient:
    """Mock HTTP client that returns fixture-backed responses.

    This client replaces HttpFetcher during E2E testing to:
    1. Return deterministic fixture content for registered URLs
    2. Block all unregistered network requests
    3. Record all request attempts for audit logging
    """

    def __init__(
        self,
        fixture_loader: FixtureLoader,
        run_id: str,
        allow_unmatched: bool = False,
    ) -> None:
        """Initialize the mock HTTP client.

        Args:
            fixture_loader: Fixture loader with URL mappings.
            run_id: Run ID for logging.
            allow_unmatched: If True, return 404 instead of blocking.
        """
        self._fixture_loader = fixture_loader
        self._run_id = run_id
        self._allow_unmatched = allow_unmatched
        self._stats = MockTransportStats()
        self._log = logger.bind(
            component="e2e",
            run_id=run_id,
        )

    @property
    def stats(self) -> MockTransportStats:
        """Get transport statistics."""
        return self._stats

    def fetch(
        self,
        source_id: str,
        url: str,
        extra_headers: dict[str, str] | None = None,  # noqa: ARG002
    ) -> FetchResult:
        """Fetch a URL using fixture-backed response.

        Args:
            source_id: Source identifier.
            url: URL to fetch.
            extra_headers: Additional headers (ignored in mock).

        Returns:
            FetchResult with fixture content or error.

        Raises:
            NetworkAccessBlockedError: If URL not registered and blocking enabled.
        """
        now = datetime.now(UTC)
        self._stats.requests_total += 1

        # Try to find fixture for URL
        fixture = self._fixture_loader.get_fixture_for_url(url)

        if fixture is not None:
            return self._handle_matched_request(source_id, url, fixture, now)

        return self._handle_unmatched_request(source_id, url, now)

    def _handle_matched_request(
        self,
        source_id: str,
        url: str,
        fixture: FixtureInfo,
        timestamp: datetime,
    ) -> FetchResult:
        """Handle a request that matched a fixture.

        Args:
            source_id: Source identifier.
            url: Requested URL.
            fixture: Matched fixture.
            timestamp: Request timestamp.

        Returns:
            FetchResult with fixture content.
        """
        self._stats.requests_matched += 1
        self._stats.request_log.append(
            RequestRecord(
                url=url,
                timestamp=timestamp,
                source_id=source_id,
                fixture_name=fixture.name,
                blocked=False,
            )
        )

        self._log.debug(
            "mock_fetch_matched",
            source_id=source_id,
            url=url,
            fixture=fixture.name,
            bytes=len(fixture.content),
        )

        return FetchResult(
            status_code=200,
            final_url=url,
            headers={
                "content-type": self._get_content_type(fixture),
                "content-length": str(len(fixture.content)),
                "x-e2e-fixture": fixture.name,
            },
            body_bytes=fixture.content,
            cache_hit=False,
            error=None,
        )

    def _handle_unmatched_request(
        self,
        source_id: str,
        url: str,
        timestamp: datetime,
    ) -> FetchResult:
        """Handle a request that did not match any fixture.

        Args:
            source_id: Source identifier.
            url: Requested URL.
            timestamp: Request timestamp.

        Returns:
            FetchResult with 404 error if allow_unmatched, else raises.

        Raises:
            NetworkAccessBlockedError: If blocking is enabled.
        """
        self._stats.requests_blocked += 1
        self._stats.request_log.append(
            RequestRecord(
                url=url,
                timestamp=timestamp,
                source_id=source_id,
                fixture_name=None,
                blocked=True,
            )
        )

        self._log.warning(
            "mock_fetch_blocked",
            source_id=source_id,
            url=url,
        )

        if not self._allow_unmatched:
            raise NetworkAccessBlockedError(url)

        return FetchResult(
            status_code=404,
            final_url=url,
            headers={},
            body_bytes=b"",
            cache_hit=False,
            error=FetchError(
                error_class=FetchErrorClass.HTTP_4XX,
                message=f"No fixture registered for URL: {url}",
                status_code=404,
            ),
        )

    def _get_content_type(self, fixture: FixtureInfo) -> str:
        """Get content type for a fixture.

        Args:
            fixture: Fixture info.

        Returns:
            Content-Type header value.
        """
        ext = fixture.path.rsplit(".", 1)[-1].lower()
        content_types: dict[str, str] = {
            "xml": "application/xml",
            "json": "application/json",
            "html": "text/html",
            "atom": "application/atom+xml",
            "rss": "application/rss+xml",
        }
        return content_types.get(ext, "application/octet-stream")

    def get_request_log(self) -> list[dict[str, object]]:
        """Get the request log as a list of dictionaries.

        Returns:
            List of request records as dictionaries.
        """
        return [
            {
                "url": r.url,
                "timestamp": r.timestamp.isoformat(),
                "source_id": r.source_id,
                "fixture_name": r.fixture_name,
                "blocked": r.blocked,
            }
            for r in self._stats.request_log
        ]
