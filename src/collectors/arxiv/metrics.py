"""Metrics for arXiv collectors.

This module provides metrics tracking for arXiv RSS and API collectors.
"""

import threading
from dataclasses import dataclass, field
from typing import TypedDict


class LatencyStats(TypedDict):
    """Latency statistics for API requests."""

    p50: float
    p90: float
    p99: float
    count: float


class MetricsSnapshot(TypedDict):
    """Snapshot of all arXiv metrics.

    Provides type-safe access to metrics data.
    """

    items_by_mode_category: dict[str, int]
    deduped_total: int
    api_latency: LatencyStats
    errors_by_type: dict[str, int]


@dataclass
class ArxivMetricsData:
    """Thread-safe container for arXiv metrics data."""

    items_by_mode_category: dict[str, int] = field(default_factory=dict)
    deduped_total: int = 0
    api_latency_samples: list[float] = field(default_factory=list)
    errors_by_type: dict[str, int] = field(default_factory=dict)


class ArxivMetrics:
    """Metrics collector for arXiv operations.

    Provides thread-safe metrics for:
    - arxiv_items_total{mode,category}
    - arxiv_deduped_total
    - arxiv_api_latency_ms
    """

    _instance: "ArxivMetrics | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self._data = ArxivMetricsData()
        self._data_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ArxivMetrics":
        """Get singleton instance.

        Returns:
            The singleton ArxivMetrics instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    def record_items(
        self,
        count: int,
        mode: str,
        category: str | None = None,
    ) -> None:
        """Record items collected.

        Args:
            count: Number of items collected.
            mode: Collection mode ('rss' or 'api').
            category: arXiv category (for RSS mode).
        """
        key = f"{mode}:{category or 'query'}"
        with self._data_lock:
            self._data.items_by_mode_category[key] = (
                self._data.items_by_mode_category.get(key, 0) + count
            )

    def record_deduped(self, count: int) -> None:
        """Record deduplicated items.

        Args:
            count: Number of items deduplicated.
        """
        with self._data_lock:
            self._data.deduped_total += count

    def record_api_latency(self, latency_ms: float) -> None:
        """Record API request latency.

        Args:
            latency_ms: Latency in milliseconds.
        """
        with self._data_lock:
            self._data.api_latency_samples.append(latency_ms)

    def record_error(self, error_type: str) -> None:
        """Record an error.

        Args:
            error_type: Type of error (e.g., 'timeout', 'malformed_atom', 'empty').
        """
        with self._data_lock:
            self._data.errors_by_type[error_type] = (
                self._data.errors_by_type.get(error_type, 0) + 1
            )

    def get_items_total(self, mode: str, category: str | None = None) -> int:
        """Get total items collected for a mode/category.

        Args:
            mode: Collection mode ('rss' or 'api').
            category: arXiv category (for RSS mode).

        Returns:
            Total items collected.
        """
        key = f"{mode}:{category or 'query'}"
        with self._data_lock:
            return self._data.items_by_mode_category.get(key, 0)

    def get_deduped_total(self) -> int:
        """Get total deduplicated items.

        Returns:
            Total items deduplicated.
        """
        with self._data_lock:
            return self._data.deduped_total

    def get_api_latency_stats(self) -> LatencyStats:
        """Get API latency statistics.

        Returns:
            LatencyStats with p50, p90, p99, and count.
        """
        with self._data_lock:
            samples = sorted(self._data.api_latency_samples)

        if not samples:
            return LatencyStats(p50=0.0, p90=0.0, p99=0.0, count=0.0)

        count = len(samples)
        return LatencyStats(
            p50=samples[int(count * 0.5)] if count > 0 else 0.0,
            p90=samples[int(count * 0.9)] if count > 0 else 0.0,
            p99=samples[int(count * 0.99)] if count > 0 else 0.0,
            count=float(count),
        )

    def get_snapshot(self) -> MetricsSnapshot:
        """Get a snapshot of all metrics.

        Returns:
            MetricsSnapshot containing all metrics with type-safe access.
        """
        with self._data_lock:
            # Copy data while holding lock to avoid race conditions.
            # Compute latency stats inline to avoid re-acquiring lock.
            samples = sorted(self._data.api_latency_samples)
            count = len(samples)
            api_latency = LatencyStats(
                p50=samples[int(count * 0.5)] if count > 0 else 0.0,
                p90=samples[int(count * 0.9)] if count > 0 else 0.0,
                p99=samples[int(count * 0.99)] if count > 0 else 0.0,
                count=float(count),
            )
            return MetricsSnapshot(
                items_by_mode_category=dict(self._data.items_by_mode_category),
                deduped_total=self._data.deduped_total,
                api_latency=api_latency,
                errors_by_type=dict(self._data.errors_by_type),
            )
