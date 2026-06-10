"""Metrics for HTML profile parsing."""

import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock


# Module-level singleton state
_metrics_instance: "HtmlProfileMetrics | None" = None
_metrics_lock: Lock = Lock()


@dataclass
class HtmlProfileMetrics:
    """Thread-safe metrics for HTML profile parsing.

    Tracks links extracted, date recovery, parse failures, and timing by domain.
    Use get_instance() for singleton access.
    """

    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    # Per-domain link counts
    links_by_domain: Counter[str] = field(default_factory=Counter)

    # Per-domain date recovery counts
    date_recovery_by_domain: Counter[str] = field(default_factory=Counter)

    # Per-domain parse failure counts
    parse_failures_by_domain: Counter[str] = field(default_factory=Counter)

    # Per-domain item pages fetched
    item_pages_by_domain: Counter[str] = field(default_factory=Counter)

    # Per-domain links filtered out
    links_filtered_by_domain: Counter[str] = field(default_factory=Counter)

    # Per-phase extraction timing (sum of durations in seconds)
    extraction_duration_by_phase: dict[str, float] = field(default_factory=dict)

    # Per-phase extraction counts
    extraction_count_by_phase: Counter[str] = field(default_factory=Counter)

    @classmethod
    def get_instance(cls) -> "HtmlProfileMetrics":
        """Get the singleton instance (thread-safe).

        Returns:
            The shared HtmlProfileMetrics instance.
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

    def record_links_found(self, domain: str, count: int) -> None:
        """Record links found for a domain.

        Args:
            domain: Domain name.
            count: Number of links found.
        """
        with self._lock:
            self.links_by_domain[domain] += count

    def record_links_filtered(self, domain: str, count: int) -> None:
        """Record links filtered out for a domain.

        Args:
            domain: Domain name.
            count: Number of links filtered out.
        """
        with self._lock:
            self.links_filtered_by_domain[domain] += count

    def record_date_recovery(self, domain: str, count: int) -> None:
        """Record dates recovered from item pages.

        Args:
            domain: Domain name.
            count: Number of dates recovered.
        """
        with self._lock:
            self.date_recovery_by_domain[domain] += count

    def record_item_pages_fetched(self, domain: str, count: int) -> None:
        """Record item pages fetched for a domain.

        Args:
            domain: Domain name.
            count: Number of item pages fetched.
        """
        with self._lock:
            self.item_pages_by_domain[domain] += count

    def record_parse_failure(self, domain: str) -> None:
        """Record a parse failure for a domain.

        Args:
            domain: Domain name.
        """
        with self._lock:
            self.parse_failures_by_domain[domain] += 1

    def record_extraction_duration(self, phase: str, duration_seconds: float) -> None:
        """Record extraction phase duration.

        Args:
            phase: Extraction phase name (e.g., 'time_element', 'meta_tags').
            duration_seconds: Duration in seconds.
        """
        with self._lock:
            if phase not in self.extraction_duration_by_phase:
                self.extraction_duration_by_phase[phase] = 0.0
            self.extraction_duration_by_phase[phase] += duration_seconds
            self.extraction_count_by_phase[phase] += 1

    @contextmanager
    def measure_phase(self, phase: str) -> Iterator[None]:
        """Context manager to measure extraction phase duration.

        Usage:
            with metrics.measure_phase('time_element'):
                # extraction code

        Args:
            phase: Extraction phase name.

        Yields:
            None.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.record_extraction_duration(phase, duration)

    def get_average_duration(self, phase: str) -> float:
        """Get average duration for an extraction phase.

        Args:
            phase: Extraction phase name.

        Returns:
            Average duration in seconds, or 0 if no data.
        """
        with self._lock:
            count = self.extraction_count_by_phase.get(phase, 0)
            if count == 0:
                return 0.0
            total = self.extraction_duration_by_phase.get(phase, 0.0)
            return total / count

    def get_links_total(self, domain: str | None = None) -> int:
        """Get total links found.

        Args:
            domain: Optional domain to filter by.

        Returns:
            Total link count.
        """
        with self._lock:
            if domain is None:
                return sum(self.links_by_domain.values())
            return self.links_by_domain[domain]

    def get_date_recovery_total(self, domain: str | None = None) -> int:
        """Get total dates recovered.

        Args:
            domain: Optional domain to filter by.

        Returns:
            Total date recovery count.
        """
        with self._lock:
            if domain is None:
                return sum(self.date_recovery_by_domain.values())
            return self.date_recovery_by_domain[domain]

    def get_parse_failures_total(self, domain: str | None = None) -> int:
        """Get total parse failures.

        Args:
            domain: Optional domain to filter by.

        Returns:
            Total failure count.
        """
        with self._lock:
            if domain is None:
                return sum(self.parse_failures_by_domain.values())
            return self.parse_failures_by_domain[domain]

    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string.
        """
        lines: list[str] = []

        with self._lock:
            # html_list_links_total
            lines.append("# HELP html_list_links_total Total links found by domain")
            lines.append("# TYPE html_list_links_total counter")
            for domain, count in sorted(self.links_by_domain.items()):
                lines.append(f'html_list_links_total{{domain="{domain}"}} {count}')

            # html_date_recovery_total
            lines.append(
                "# HELP html_date_recovery_total Total dates recovered by domain"
            )
            lines.append("# TYPE html_date_recovery_total counter")
            for domain, count in sorted(self.date_recovery_by_domain.items()):
                lines.append(f'html_date_recovery_total{{domain="{domain}"}} {count}')

            # html_parse_failures_total
            lines.append(
                "# HELP html_parse_failures_total Total parse failures by domain"
            )
            lines.append("# TYPE html_parse_failures_total counter")
            for domain, count in sorted(self.parse_failures_by_domain.items()):
                lines.append(f'html_parse_failures_total{{domain="{domain}"}} {count}')

        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Export metrics as dictionary.

        Returns:
            Dictionary representation of all metrics.
        """
        with self._lock:
            return {
                "links_by_domain": dict(self.links_by_domain),
                "date_recovery_by_domain": dict(self.date_recovery_by_domain),
                "parse_failures_by_domain": dict(self.parse_failures_by_domain),
                "item_pages_by_domain": dict(self.item_pages_by_domain),
                "links_filtered_by_domain": dict(self.links_filtered_by_domain),
                "extraction_duration_by_phase": dict(self.extraction_duration_by_phase),
                "extraction_count_by_phase": dict(self.extraction_count_by_phase),
            }
