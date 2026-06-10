"""Metrics for source status tracking."""

from collections import Counter
from threading import Lock


class StatusMetrics:
    """Collects metrics for source status computation.

    Provides thread-safe counters for:
    - sources_failed_total{source_id, reason_code}
    - sources_cannot_confirm_total{source_id}

    Metrics are designed to be exportable to Prometheus or similar systems.
    """

    _instance: "StatusMetrics | None" = None
    _lock = Lock()

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self._sources_failed: Counter[tuple[str, str]] = Counter()
        self._sources_cannot_confirm: Counter[str] = Counter()
        self._lock = Lock()

    @classmethod
    def get_instance(cls) -> "StatusMetrics":
        """Get the singleton metrics instance.

        Returns:
            The shared StatusMetrics instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    def record_source_failed(self, source_id: str, reason_code: str) -> None:
        """Record a source failure.

        Args:
            source_id: Identifier of the source.
            reason_code: Reason code for the failure.
        """
        with self._lock:
            self._sources_failed[(source_id, reason_code)] += 1

    def record_source_cannot_confirm(self, source_id: str) -> None:
        """Record a source that cannot be confirmed.

        Args:
            source_id: Identifier of the source.
        """
        with self._lock:
            self._sources_cannot_confirm[source_id] += 1

    def get_sources_failed_total(self) -> dict[tuple[str, str], int]:
        """Get all failed source counts.

        Returns:
            Dict mapping (source_id, reason_code) to count.
        """
        with self._lock:
            return dict(self._sources_failed)

    def get_sources_cannot_confirm_total(self) -> dict[str, int]:
        """Get all cannot-confirm source counts.

        Returns:
            Dict mapping source_id to count.
        """
        with self._lock:
            return dict(self._sources_cannot_confirm)

    def get_failed_count_for_source(self, source_id: str) -> int:
        """Get total failure count for a specific source.

        Args:
            source_id: Identifier of the source.

        Returns:
            Total failure count.
        """
        with self._lock:
            return sum(
                count
                for (sid, _), count in self._sources_failed.items()
                if sid == source_id
            )

    def reset(self) -> None:
        """Reset all metrics (for testing)."""
        with self._lock:
            self._sources_failed.clear()
            self._sources_cannot_confirm.clear()
