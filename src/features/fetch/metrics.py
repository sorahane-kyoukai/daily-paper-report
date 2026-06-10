"""Metrics collection for the HTTP fetch layer."""

from dataclasses import dataclass, field
from typing import ClassVar

from src.features.fetch.models import FetchErrorClass


@dataclass
class FetchMetrics:
    """Metrics for HTTP fetch operations.

    Singleton class that tracks fetch-related metrics including
    request counts, cache hits, retries, and failures.
    """

    http_requests_total: dict[int, int] = field(default_factory=dict)
    http_cache_hits_total: int = 0
    http_retry_total: int = 0
    http_failures_total: dict[str, int] = field(default_factory=dict)
    http_bytes_total: int = 0
    http_duration_ms_total: float = 0.0
    http_request_count: int = 0

    _instance: ClassVar["FetchMetrics | None"] = None

    @classmethod
    def get_instance(cls) -> "FetchMetrics":
        """Get singleton metrics instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset metrics (primarily for testing)."""
        cls._instance = None

    def record_request(self, status_code: int, bytes_received: int) -> None:
        """Record a completed HTTP request.

        Args:
            status_code: HTTP status code.
            bytes_received: Number of bytes received.
        """
        self.http_requests_total[status_code] = (
            self.http_requests_total.get(status_code, 0) + 1
        )
        self.http_bytes_total += bytes_received
        self.http_request_count += 1

    def record_cache_hit(self) -> None:
        """Record a cache hit (304 response)."""
        self.http_cache_hits_total += 1

    def record_retry(self) -> None:
        """Record a retry attempt."""
        self.http_retry_total += 1

    def record_failure(self, error_class: FetchErrorClass) -> None:
        """Record a fetch failure.

        Args:
            error_class: Classification of the failure.
        """
        key = error_class.value
        self.http_failures_total[key] = self.http_failures_total.get(key, 0) + 1

    def record_duration(self, duration_ms: float) -> None:
        """Record request duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self.http_duration_ms_total += duration_ms

    def to_dict(self) -> dict[str, int | float | dict[str, int] | dict[int, int]]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "http_requests_total": dict(self.http_requests_total),
            "http_cache_hits_total": self.http_cache_hits_total,
            "http_retry_total": self.http_retry_total,
            "http_failures_total": dict(self.http_failures_total),
            "http_bytes_total": self.http_bytes_total,
            "http_duration_ms_total": self.http_duration_ms_total,
            "http_request_count": self.http_request_count,
        }

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average request duration.

        Returns:
            Average duration in milliseconds.
        """
        if self.http_request_count == 0:
            return 0.0
        return self.http_duration_ms_total / self.http_request_count
