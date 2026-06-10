"""Metrics collection for platform collectors."""

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock

from src.collectors.platform.constants import (
    PLATFORM_GITHUB,
    PLATFORM_HUGGINGFACE,
    PLATFORM_OPENREVIEW,
)


# Module-level singleton state
_metrics_instance: "PlatformMetrics | None" = None
_metrics_lock: Lock = Lock()


@dataclass
class PlatformMetrics:
    """Thread-safe metrics for platform collector operations.

    Tracks API calls, rate limit events, and items collected per platform.
    Use get_instance() for singleton access.
    """

    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    # API calls by platform
    api_calls: Counter[str] = field(default_factory=Counter)

    # Rate limit events by platform
    rate_limit_events: Counter[str] = field(default_factory=Counter)

    # Items emitted by platform
    items_by_platform: Counter[str] = field(default_factory=Counter)

    # Errors by platform and type
    errors_by_platform: Counter[tuple[str, str]] = field(default_factory=Counter)

    @classmethod
    def get_instance(cls) -> "PlatformMetrics":
        """Get the singleton instance (thread-safe).

        Returns:
            The shared PlatformMetrics instance.
        """
        global _metrics_instance  # noqa: PLW0603
        if _metrics_instance is None:
            with _metrics_lock:
                if _metrics_instance is None:
                    _metrics_instance = cls()
        return _metrics_instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        global _metrics_instance  # noqa: PLW0603
        with _metrics_lock:
            _metrics_instance = None

    def record_api_call(self, platform: str) -> None:
        """Record an API call for a platform.

        Args:
            platform: Platform identifier.
        """
        with self._lock:
            self.api_calls[platform] += 1

    def record_rate_limit_event(self, platform: str) -> None:
        """Record a rate limit event for a platform.

        Args:
            platform: Platform identifier.
        """
        with self._lock:
            self.rate_limit_events[platform] += 1

    def record_items(self, platform: str, count: int) -> None:
        """Record items collected from a platform.

        Args:
            platform: Platform identifier.
            count: Number of items.
        """
        with self._lock:
            self.items_by_platform[platform] += count

    def record_error(self, platform: str, error_type: str) -> None:
        """Record an error for a platform.

        Args:
            platform: Platform identifier.
            error_type: Type of error (e.g., 'auth', 'parse', 'fetch').
        """
        with self._lock:
            self.errors_by_platform[(platform, error_type)] += 1

    def get_api_calls_total(self, platform: str | None = None) -> int:
        """Get total API calls.

        Args:
            platform: Optional platform to filter by.

        Returns:
            Total API call count.
        """
        with self._lock:
            if platform is None:
                return sum(self.api_calls.values())
            return self.api_calls.get(platform, 0)

    def get_rate_limit_events_total(self, platform: str | None = None) -> int:
        """Get total rate limit events.

        Args:
            platform: Optional platform to filter by.

        Returns:
            Total rate limit event count.
        """
        with self._lock:
            if platform is None:
                return sum(self.rate_limit_events.values())
            return self.rate_limit_events.get(platform, 0)

    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string.
        """
        lines: list[str] = []

        with self._lock:
            # github_api_calls_total
            lines.append("# HELP github_api_calls_total Total GitHub API calls")
            lines.append("# TYPE github_api_calls_total counter")
            lines.append(
                f"github_api_calls_total {self.api_calls.get(PLATFORM_GITHUB, 0)}"
            )

            # hf_api_calls_total
            lines.append("# HELP hf_api_calls_total Total HuggingFace API calls")
            lines.append("# TYPE hf_api_calls_total counter")
            lines.append(
                f"hf_api_calls_total {self.api_calls.get(PLATFORM_HUGGINGFACE, 0)}"
            )

            # openreview_api_calls_total
            lines.append("# HELP openreview_api_calls_total Total OpenReview API calls")
            lines.append("# TYPE openreview_api_calls_total counter")
            lines.append(
                f"openreview_api_calls_total {self.api_calls.get(PLATFORM_OPENREVIEW, 0)}"
            )

            # platform_rate_limit_events_total
            lines.append(
                "# HELP platform_rate_limit_events_total Rate limit events by platform"
            )
            lines.append("# TYPE platform_rate_limit_events_total counter")
            for platform, count in sorted(self.rate_limit_events.items()):
                lines.append(
                    f'platform_rate_limit_events_total{{platform="{platform}"}} {count}'
                )

        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Export metrics as dictionary.

        Returns:
            Dictionary representation of all metrics.
        """
        with self._lock:
            return {
                "api_calls": dict(self.api_calls),
                "rate_limit_events": dict(self.rate_limit_events),
                "items_by_platform": dict(self.items_by_platform),
                "errors_by_platform": {
                    f"{p}:{t}": c for (p, t), c in self.errors_by_platform.items()
                },
            }
