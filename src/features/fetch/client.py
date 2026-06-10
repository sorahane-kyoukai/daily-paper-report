"""HTTP client with caching, retries, and failure isolation."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from urllib.parse import urlparse

import httpx
import structlog

from src.features.fetch.cache import CacheManager
from src.features.fetch.config import FetchConfig
from src.features.fetch.constants import (
    DEFAULT_CHUNK_SIZE,
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_NOT_MODIFIED,
    HTTP_STATUS_OK_MAX,
    HTTP_STATUS_OK_MIN,
    HTTP_STATUS_SERVER_ERROR_MAX,
    HTTP_STATUS_SERVER_ERROR_MIN,
    HTTP_STATUS_TOO_MANY_REQUESTS,
    MAX_RETRY_AFTER_SECONDS,
)
from src.features.fetch.metrics import FetchMetrics
from src.features.fetch.models import (
    FetchError,
    FetchErrorClass,
    FetchResult,
    ResponseSizeExceededError,
)
from src.features.fetch.redact import redact_headers, redact_url_credentials
from src.features.store.store import StateStore


logger = structlog.get_logger()


class HttpFetcher:
    """HTTP client with caching, retries, and failure isolation.

    Provides robust HTTP GET operations with:
    - ETag/Last-Modified conditional requests
    - Configurable retry policy with exponential backoff
    - Maximum response size enforcement
    - Header redaction for logging
    - Metrics collection
    """

    def __init__(
        self,
        config: FetchConfig,
        store: StateStore,
        run_id: str,
    ) -> None:
        """Initialize the HTTP fetcher.

        Args:
            config: Fetch configuration.
            store: State store for http_cache persistence.
            run_id: Unique run identifier for logging.
        """
        self._config = config
        self._run_id = run_id
        self._metrics = FetchMetrics.get_instance()
        self._cache = CacheManager(store, run_id)
        self._log = logger.bind(
            component="fetch",
            run_id=run_id,
        )

    def fetch(
        self,
        source_id: str,
        url: str,
        extra_headers: dict[str, str] | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
    ) -> FetchResult:
        """Fetch a URL with caching and retry support.

        Args:
            source_id: Identifier for the source being fetched.
            url: The URL to fetch.
            extra_headers: Additional headers to include.
            max_retries: Optional override for the configured retry count.
            timeout_seconds: Optional override for the configured request timeout.

        Returns:
            FetchResult with status, body, and cache information.
        """
        start_time_ns = time.perf_counter_ns()
        parsed = urlparse(url)
        domain = parsed.netloc

        log = self._log.bind(
            source_id=source_id,
            url=redact_url_credentials(url),
            domain=domain,
        )

        # Build headers
        headers = self._build_headers(domain, extra_headers)

        # Add conditional request headers from cache
        conditional_headers = self._cache.get_conditional_headers(source_id)
        headers.update(conditional_headers)

        # Execute with retries
        result = self._execute_with_retry(
            url=url,
            domain=domain,
            headers=headers,
            log=log,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

        # Calculate duration
        duration_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000
        self._metrics.record_duration(duration_ms)

        # Update http_cache
        self._cache.update_from_result(source_id, result)

        # Log result
        log.info(
            "fetch_complete",
            status_code=result.status_code,
            cache_hit=result.cache_hit,
            bytes=result.body_size,
            duration_ms=round(duration_ms, 2),
            error_class=result.error.error_class.value if result.error else None,
        )

        return result

    def _build_headers(
        self,
        domain: str,
        extra_headers: dict[str, str] | None,
    ) -> dict[str, str]:
        """Build request headers.

        Args:
            domain: Request domain.
            extra_headers: Additional headers from caller.

        Returns:
            Complete headers dictionary.
        """
        headers: dict[str, str] = {
            "User-Agent": self._config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        # Add domain-specific headers
        domain_headers = self._config.get_headers_for_domain(domain)
        headers.update(domain_headers)

        # Add caller-provided headers
        if extra_headers:
            headers.update(extra_headers)

        return headers

    def _execute_with_retry(
        self,
        url: str,
        domain: str,
        headers: dict[str, str],
        log: structlog.stdlib.BoundLogger,
        *,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
    ) -> FetchResult:
        """Execute request with retry logic.

        Args:
            url: URL to fetch.
            domain: Request domain.
            headers: Request headers.
            log: Bound logger.

        Returns:
            FetchResult from the request.
        """
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._config.get_timeout_for_domain(domain)
        )
        policy = (
            self._config.retry_policy
            if max_retries is None
            else self._config.retry_policy.model_copy(
                update={"max_retries": max_retries}
            )
        )
        last_error: FetchError | None = None

        for attempt in range(policy.max_retries + 1):
            if attempt > 0:
                delay_ms = policy.get_delay_ms(attempt - 1)
                self._metrics.record_retry()
                log.debug(
                    "retry_attempt",
                    attempt=attempt,
                    delay_ms=delay_ms,
                    max_retries=policy.max_retries,
                )
                time.sleep(delay_ms / 1000.0)

            result = self._execute_single(
                url=url,
                headers=headers,
                timeout=timeout,
                log=log,
                attempt=attempt,
            )

            # Success or non-retryable error
            if result.error is None or not policy.should_retry(result.error, attempt):
                return result

            last_error = result.error

            # Handle 429 Retry-After
            if result.error.error_class == FetchErrorClass.RATE_LIMITED:
                retry_after = result.error.retry_after
                if retry_after and retry_after > 0:
                    log.info(
                        "rate_limited",
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    time.sleep(min(retry_after, MAX_RETRY_AFTER_SECONDS))

        # All retries exhausted
        self._metrics.record_failure(
            last_error.error_class if last_error else FetchErrorClass.UNKNOWN
        )
        return FetchResult(
            status_code=last_error.status_code or 0 if last_error else 0,
            final_url=url,
            headers={},
            body_bytes=b"",
            cache_hit=False,
            error=last_error,
        )

    def _execute_single(
        self,
        url: str,
        headers: dict[str, str],
        timeout: float,
        log: structlog.stdlib.BoundLogger,
        attempt: int,
    ) -> FetchResult:
        """Execute a single HTTP request.

        Args:
            url: URL to fetch.
            headers: Request headers.
            timeout: Request timeout in seconds.
            log: Bound logger.
            attempt: Current attempt number.

        Returns:
            FetchResult from the request.
        """
        log = log.bind(attempt=attempt, headers=redact_headers(headers))

        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
            ) as client:
                response = client.get(url, headers=headers)

                # Check response size with streaming
                content_length = response.headers.get("content-length")
                if content_length:
                    size = int(content_length)
                    if size > self._config.max_response_size_bytes:
                        size_error = FetchError(
                            error_class=FetchErrorClass.RESPONSE_SIZE_EXCEEDED,
                            message=f"Response size {size} exceeds limit {self._config.max_response_size_bytes}",
                            status_code=response.status_code,
                        )
                        return FetchResult(
                            status_code=response.status_code,
                            final_url=str(response.url),
                            headers=dict(response.headers),
                            body_bytes=b"",
                            cache_hit=False,
                            error=size_error,
                        )

                # Read body with size limit
                body = self._read_body_with_limit(response)

                # Record metrics
                self._metrics.record_request(response.status_code, len(body))

                # Handle 304 Not Modified
                if response.status_code == HTTP_STATUS_NOT_MODIFIED:
                    self._metrics.record_cache_hit()
                    return FetchResult(
                        status_code=HTTP_STATUS_NOT_MODIFIED,
                        final_url=str(response.url),
                        headers=dict(response.headers),
                        body_bytes=b"",
                        cache_hit=True,
                        error=None,
                    )

                # Handle error status codes
                http_error = self._classify_http_error(
                    response.status_code, response.headers
                )
                return FetchResult(
                    status_code=response.status_code,
                    final_url=str(response.url),
                    headers=dict(response.headers),
                    body_bytes=body,
                    cache_hit=False,
                    error=http_error,
                )

        except httpx.TimeoutException as e:
            error = FetchError(
                error_class=FetchErrorClass.NETWORK_TIMEOUT,
                message=f"Request timed out: {e}",
            )
            return FetchResult(
                status_code=0,
                final_url=url,
                headers={},
                body_bytes=b"",
                cache_hit=False,
                error=error,
            )

        except httpx.ConnectError as e:
            error = FetchError(
                error_class=FetchErrorClass.CONNECTION_ERROR,
                message=f"Connection failed: {e}",
            )
            return FetchResult(
                status_code=0,
                final_url=url,
                headers={},
                body_bytes=b"",
                cache_hit=False,
                error=error,
            )

        except Exception as e:  # noqa: BLE001
            error = FetchError(
                error_class=FetchErrorClass.UNKNOWN,
                message=f"Unexpected error: {e}",
            )
            return FetchResult(
                status_code=0,
                final_url=url,
                headers={},
                body_bytes=b"",
                cache_hit=False,
                error=error,
            )

    def _read_body_with_limit(self, response: httpx.Response) -> bytes:
        """Read response body with size limit.

        Args:
            response: HTTP response.

        Returns:
            Response body bytes.

        Raises:
            FetchError if size limit exceeded.
        """
        buffer = BytesIO()
        total_read = 0
        max_size = self._config.max_response_size_bytes

        for chunk in response.iter_bytes(chunk_size=DEFAULT_CHUNK_SIZE):
            total_read += len(chunk)
            if total_read > max_size:
                msg = (
                    f"Response size exceeded limit of {max_size} bytes "
                    f"(read {total_read} bytes)"
                )
                raise ResponseSizeExceededError(msg)
            buffer.write(chunk)

        return buffer.getvalue()

    def _classify_http_error(
        self,
        status_code: int,
        headers: httpx.Headers,
    ) -> FetchError | None:
        """Classify HTTP status code as error.

        Args:
            status_code: HTTP status code.
            headers: Response headers.

        Returns:
            FetchError if status indicates error, None otherwise.
        """
        if HTTP_STATUS_OK_MIN <= status_code < HTTP_STATUS_OK_MAX:
            return None

        if status_code == HTTP_STATUS_TOO_MANY_REQUESTS:
            retry_after = self._parse_retry_after(headers.get("retry-after"))
            return FetchError(
                error_class=FetchErrorClass.RATE_LIMITED,
                message="Rate limited (429 Too Many Requests)",
                status_code=status_code,
                retry_after=retry_after,
            )

        if HTTP_STATUS_BAD_REQUEST <= status_code < HTTP_STATUS_SERVER_ERROR_MIN:
            return FetchError(
                error_class=FetchErrorClass.HTTP_4XX,
                message=f"Client error ({status_code})",
                status_code=status_code,
            )

        if HTTP_STATUS_SERVER_ERROR_MIN <= status_code < HTTP_STATUS_SERVER_ERROR_MAX:
            return FetchError(
                error_class=FetchErrorClass.HTTP_5XX,
                message=f"Server error ({status_code})",
                status_code=status_code,
            )

        return None

    def _parse_retry_after(self, value: str | None) -> int | None:
        """Parse Retry-After header value.

        Args:
            value: Header value (seconds or HTTP date).

        Returns:
            Seconds to wait, or None if not parseable.
        """
        if not value:
            return None

        # Try parsing as integer seconds
        try:
            return int(value)
        except ValueError:
            pass

        # Try parsing as HTTP date
        try:
            dt = parsedate_to_datetime(value)
            delta = dt - datetime.now(UTC)
            return max(0, int(delta.total_seconds()))
        except (ValueError, TypeError):
            pass

        return None
