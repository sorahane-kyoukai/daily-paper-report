"""Data models for the HTTP fetch layer."""

import random
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.features.fetch.constants import HTTP_STATUS_OK_MAX, HTTP_STATUS_OK_MIN


class FetchErrorClass(str, Enum):
    """Classification of fetch errors for metrics and retry decisions.

    - NETWORK_TIMEOUT: Request timed out
    - CONNECTION_ERROR: Could not establish connection
    - RESPONSE_SIZE_EXCEEDED: Response exceeded max size limit
    - HTTP_4XX: Non-retryable 4xx client error (except 429)
    - HTTP_5XX: Retryable 5xx server error
    - RATE_LIMITED: 429 Too Many Requests
    - SSL_ERROR: SSL/TLS certificate or handshake error
    - UNKNOWN: Unclassified error
    """

    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    RESPONSE_SIZE_EXCEEDED = "RESPONSE_SIZE_EXCEEDED"
    HTTP_4XX = "HTTP_4XX"
    HTTP_5XX = "HTTP_5XX"
    RATE_LIMITED = "RATE_LIMITED"
    SSL_ERROR = "SSL_ERROR"
    UNKNOWN = "UNKNOWN"


class FetchError(BaseModel):
    """Typed error from a fetch operation.

    Provides structured information about what went wrong during a fetch,
    enabling proper retry decisions and error reporting.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_class: FetchErrorClass = Field(description="Classification of the error")
    message: Annotated[str, Field(min_length=1, description="Human-readable message")]
    status_code: int | None = Field(
        default=None, description="HTTP status code if available"
    )
    retry_after: int | None = Field(
        default=None, description="Retry-After seconds (for 429)"
    )


class FetchResult(BaseModel):
    """Result of a fetch operation.

    Contains the response data or error information from an HTTP fetch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    status_code: int = Field(
        ge=0,
        le=599,
        description="HTTP status code, or 0 when no HTTP response was received",
    )
    final_url: Annotated[
        str, Field(min_length=1, description="Final URL after redirects")
    ]
    headers: dict[str, str] = Field(
        default_factory=dict, description="Response headers"
    )
    body_bytes: bytes = Field(default=b"", description="Response body")
    cache_hit: bool = Field(
        default=False, description="Whether response was from cache"
    )
    error: FetchError | None = Field(
        default=None, description="Error details if fetch failed"
    )

    @property
    def is_success(self) -> bool:
        """Check if the fetch was successful (2xx status, no error)."""
        return (
            self.error is None
            and HTTP_STATUS_OK_MIN <= self.status_code < HTTP_STATUS_OK_MAX
        )

    @property
    def body_size(self) -> int:
        """Get the size of the response body in bytes."""
        return len(self.body_bytes)


class RetryPolicy(BaseModel):
    """Configuration for retry behavior.

    Controls how many times to retry and the backoff strategy.
    Uses exponential backoff: delay = base_delay_ms * (exponential_base ^ attempt)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_retries: Annotated[int, Field(ge=0, le=10)] = 3
    base_delay_ms: Annotated[int, Field(ge=0, le=60000)] = 1000
    max_delay_ms: Annotated[int, Field(ge=0, le=300000)] = 30000
    exponential_base: Annotated[float, Field(ge=1.0, le=5.0)] = 2.0
    jitter_factor: Annotated[float, Field(ge=0.0, le=1.0)] = 0.1

    def should_retry(self, error: FetchError, attempt: int) -> bool:
        """Determine if a request should be retried.

        Args:
            error: The error that occurred.
            attempt: Current attempt number (0-indexed).

        Returns:
            True if the request should be retried.
        """
        if attempt >= self.max_retries:
            return False

        # Retry on network issues and 5xx
        retryable_classes = {
            FetchErrorClass.NETWORK_TIMEOUT,
            FetchErrorClass.CONNECTION_ERROR,
            FetchErrorClass.HTTP_5XX,
            FetchErrorClass.RATE_LIMITED,
        }

        return error.error_class in retryable_classes

    def get_delay_ms(self, attempt: int) -> int:
        """Calculate delay before the next retry attempt.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in milliseconds.
        """
        delay = self.base_delay_ms * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay_ms)

        # Add jitter to prevent thundering herd
        jitter = delay * self.jitter_factor * random.random()  # noqa: S311
        return int(delay + jitter)


class ResponseSizeExceededError(Exception):
    """Raised when response size exceeds the configured limit."""
