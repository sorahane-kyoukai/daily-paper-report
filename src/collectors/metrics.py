"""Metrics collection for the collector framework."""

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock

from src.collectors.errors import CollectorErrorClass


# Module-level singleton state (proper pattern for thread-safe singleton)
_metrics_instance: "CollectorMetrics | None" = None
_metrics_lock: Lock = Lock()


@dataclass
class CollectorMetrics:
    """Thread-safe metrics for collector operations.

    Tracks items collected, failures, and timing information per source.
    Use get_instance() for singleton access.
    """

    # Instance-level lock for thread-safe operations
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    # Per-source item counts by kind
    items_by_source_kind: Counter[tuple[str, str]] = field(default_factory=Counter)

    # Per-source failure counts by error class
    failures_by_source_error: Counter[tuple[str, str]] = field(default_factory=Counter)

    # Per-source duration in milliseconds
    duration_by_source: dict[str, float] = field(default_factory=dict)

    # Total items emitted
    total_items: int = 0

    # Total failures
    total_failures: int = 0

    # Total sources processed
    total_sources: int = 0

    @classmethod
    def get_instance(cls) -> "CollectorMetrics":
        """Get the singleton instance (thread-safe).

        Returns:
            The shared CollectorMetrics instance.
        """
        global _metrics_instance  # noqa: PLW0603
        if _metrics_instance is None:
            with _metrics_lock:
                # Double-checked locking
                if _metrics_instance is None:
                    _metrics_instance = cls()
        return _metrics_instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        global _metrics_instance  # noqa: PLW0603
        with _metrics_lock:
            _metrics_instance = None

    def record_items(
        self,
        source_id: str,
        kind: str,
        count: int,
    ) -> None:
        """Record items collected from a source.

        Args:
            source_id: Identifier of the source.
            kind: Kind of items collected.
            count: Number of items.
        """
        with self._lock:
            self.items_by_source_kind[(source_id, kind)] += count
            self.total_items += count

    def record_failure(
        self,
        source_id: str,
        error_class: CollectorErrorClass,
    ) -> None:
        """Record a collector failure.

        Args:
            source_id: Identifier of the source.
            error_class: Classification of the error.
        """
        with self._lock:
            self.failures_by_source_error[(source_id, error_class.value)] += 1
            self.total_failures += 1

    def record_duration(
        self,
        source_id: str,
        duration_ms: float,
    ) -> None:
        """Record collection duration for a source.

        Args:
            source_id: Identifier of the source.
            duration_ms: Duration in milliseconds.
        """
        with self._lock:
            self.duration_by_source[source_id] = duration_ms
            self.total_sources += 1

    def get_items_total(self, source_id: str | None = None) -> int:
        """Get total items collected.

        Args:
            source_id: Optional source to filter by.

        Returns:
            Total item count.
        """
        with self._lock:
            if source_id is None:
                return self.total_items
            return sum(
                count
                for (sid, _), count in self.items_by_source_kind.items()
                if sid == source_id
            )

    def get_failures_total(self, source_id: str | None = None) -> int:
        """Get total failures.

        Args:
            source_id: Optional source to filter by.

        Returns:
            Total failure count.
        """
        with self._lock:
            if source_id is None:
                return self.total_failures
            return sum(
                count
                for (sid, _), count in self.failures_by_source_error.items()
                if sid == source_id
            )

    def get_duration(self, source_id: str) -> float | None:
        """Get duration for a source.

        Args:
            source_id: Source identifier.

        Returns:
            Duration in milliseconds, or None if not recorded.
        """
        with self._lock:
            return self.duration_by_source.get(source_id)

    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string.
        """
        lines: list[str] = []

        # collector_items_total
        lines.append(
            "# HELP collector_items_total Total items collected by source and kind"
        )
        lines.append("# TYPE collector_items_total counter")
        with self._lock:
            for (source_id, kind), count in sorted(self.items_by_source_kind.items()):
                lines.append(
                    f'collector_items_total{{source_id="{source_id}",kind="{kind}"}} {count}'
                )

            # collector_failures_total
            lines.append(
                "# HELP collector_failures_total Total failures by source and error class"
            )
            lines.append("# TYPE collector_failures_total counter")
            for (source_id, error_class), count in sorted(
                self.failures_by_source_error.items()
            ):
                lines.append(
                    f'collector_failures_total{{source_id="{source_id}",error_class="{error_class}"}} {count}'
                )

            # collector_duration_ms
            lines.append("# HELP collector_duration_ms Collection duration by source")
            lines.append("# TYPE collector_duration_ms gauge")
            for source_id, duration in sorted(self.duration_by_source.items()):
                lines.append(
                    f'collector_duration_ms{{source_id="{source_id}"}} {duration:.2f}'
                )

        return "\n".join(lines)

    def to_dict(
        self,
    ) -> dict[str, object]:
        """Export metrics as dictionary.

        Returns:
            Dictionary representation of all metrics.
        """
        with self._lock:
            return {
                "total_items": self.total_items,
                "total_failures": self.total_failures,
                "total_sources": self.total_sources,
                "items_by_source_kind": dict(self.items_by_source_kind),
                "failures_by_source_error": dict(self.failures_by_source_error),
                "duration_by_source": dict(self.duration_by_source),
            }
