"""Metrics collection for the state store."""

from dataclasses import dataclass, field
from typing import ClassVar, Protocol


class MetricsRecorder(Protocol):
    """Protocol for metrics recording.

    This protocol defines the interface for recording store metrics,
    enabling dependency injection and improved testability.

    Implementations should be thread-safe if used in concurrent contexts.
    """

    def record_upsert(self) -> None:
        """Record a new item upsert."""
        ...

    def record_update(self) -> None:
        """Record an item update (content_hash changed)."""
        ...

    def record_unchanged(self) -> None:
        """Record an unchanged item."""
        ...

    def record_tx_duration(self, duration_ms: float) -> None:
        """Record transaction duration in milliseconds."""
        ...

    def record_last_success_age(self, age_seconds: float) -> None:
        """Record age of last successful run in seconds."""
        ...

    def record_items_pruned(self, count: int) -> None:
        """Record number of items pruned."""
        ...

    def record_runs_pruned(self, count: int) -> None:
        """Record number of runs pruned."""
        ...


@dataclass
class NullMetricsRecorder:
    """No-op metrics recorder for testing.

    This implementation discards all metrics, useful for tests that
    don't need to verify metrics behavior.
    """

    def record_upsert(self) -> None:
        """No-op."""

    def record_update(self) -> None:
        """No-op."""

    def record_unchanged(self) -> None:
        """No-op."""

    def record_tx_duration(self, duration_ms: float) -> None:  # noqa: ARG002
        """No-op."""

    def record_last_success_age(self, age_seconds: float) -> None:  # noqa: ARG002
        """No-op."""

    def record_items_pruned(self, count: int) -> None:  # noqa: ARG002
        """No-op."""

    def record_runs_pruned(self, count: int) -> None:  # noqa: ARG002
        """No-op."""


@dataclass
class StoreMetrics:
    """Metrics for state store operations.

    Attributes:
        db_upserts_total: Total number of item upserts (new items).
        db_updates_total: Total number of item updates (changed hash).
        db_unchanged_total: Total number of unchanged items.
        db_tx_duration_ms: Cumulative transaction duration in milliseconds.
        db_tx_count: Number of transactions.
        last_success_age_seconds: Age of last successful run in seconds.
        items_pruned_total: Total items pruned by retention.
        runs_pruned_total: Total runs pruned by retention.
    """

    db_upserts_total: int = 0
    db_updates_total: int = 0
    db_unchanged_total: int = 0
    db_tx_duration_ms: float = 0.0
    db_tx_count: int = 0
    last_success_age_seconds: float = 0.0
    items_pruned_total: int = 0
    runs_pruned_total: int = 0

    _instance: ClassVar["StoreMetrics | None"] = None

    @classmethod
    def get_instance(cls) -> "StoreMetrics":
        """Get singleton metrics instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset metrics (primarily for testing)."""
        cls._instance = None

    def record_upsert(self) -> None:
        """Record a new item upsert."""
        self.db_upserts_total += 1

    def record_update(self) -> None:
        """Record an item update."""
        self.db_updates_total += 1

    def record_unchanged(self) -> None:
        """Record an unchanged item."""
        self.db_unchanged_total += 1

    def record_tx_duration(self, duration_ms: float) -> None:
        """Record transaction duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self.db_tx_duration_ms += duration_ms
        self.db_tx_count += 1

    def record_last_success_age(self, age_seconds: float) -> None:
        """Record age of last successful run.

        Args:
            age_seconds: Age in seconds.
        """
        self.last_success_age_seconds = age_seconds

    def record_items_pruned(self, count: int) -> None:
        """Record pruned items.

        Args:
            count: Number of items pruned.
        """
        self.items_pruned_total += count

    def record_runs_pruned(self, count: int) -> None:
        """Record pruned runs.

        Args:
            count: Number of runs pruned.
        """
        self.runs_pruned_total += count

    def to_dict(self) -> dict[str, float | int]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "db_upserts_total": self.db_upserts_total,
            "db_updates_total": self.db_updates_total,
            "db_unchanged_total": self.db_unchanged_total,
            "db_tx_duration_ms": self.db_tx_duration_ms,
            "db_tx_count": self.db_tx_count,
            "last_success_age_seconds": self.last_success_age_seconds,
            "items_pruned_total": self.items_pruned_total,
            "runs_pruned_total": self.runs_pruned_total,
        }

    @property
    def avg_tx_duration_ms(self) -> float:
        """Calculate average transaction duration.

        Returns:
            Average duration in milliseconds.
        """
        if self.db_tx_count == 0:
            return 0.0
        return self.db_tx_duration_ms / self.db_tx_count


@dataclass
class TransactionContext:
    """Context for a single transaction with timing.

    Attributes:
        tx_id: Unique transaction identifier.
        start_time_ns: Start time in nanoseconds.
        operation: The operation being performed.
    """

    tx_id: str
    start_time_ns: int
    operation: str
    affected_rows: int = field(default=0)

    def add_affected_rows(self, rows: int) -> None:
        """Add to the affected row count.

        Args:
            rows: Number of rows affected.
        """
        self.affected_rows += rows
