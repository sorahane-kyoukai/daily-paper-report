"""Unit tests for status metrics."""

from src.features.status.metrics import StatusMetrics


class TestStatusMetrics:
    """Tests for StatusMetrics class."""

    def setup_method(self) -> None:
        """Reset metrics before each test."""
        StatusMetrics.reset_instance()

    def teardown_method(self) -> None:
        """Reset metrics after each test."""
        StatusMetrics.reset_instance()

    def test_singleton_instance(self) -> None:
        """StatusMetrics is a singleton."""
        m1 = StatusMetrics.get_instance()
        m2 = StatusMetrics.get_instance()
        assert m1 is m2

    def test_record_source_failed(self) -> None:
        """Record source failure increments counter."""
        metrics = StatusMetrics.get_instance()
        metrics.record_source_failed("source-1", "FETCH_TIMEOUT")
        metrics.record_source_failed("source-1", "FETCH_TIMEOUT")
        metrics.record_source_failed("source-2", "PARSE_ERROR")

        totals = metrics.get_sources_failed_total()
        assert totals[("source-1", "FETCH_TIMEOUT")] == 2
        assert totals[("source-2", "PARSE_ERROR")] == 1

    def test_record_source_cannot_confirm(self) -> None:
        """Record cannot confirm increments counter."""
        metrics = StatusMetrics.get_instance()
        metrics.record_source_cannot_confirm("source-1")
        metrics.record_source_cannot_confirm("source-1")
        metrics.record_source_cannot_confirm("source-2")

        totals = metrics.get_sources_cannot_confirm_total()
        assert totals["source-1"] == 2
        assert totals["source-2"] == 1

    def test_get_failed_count_for_source(self) -> None:
        """Get total failure count for specific source."""
        metrics = StatusMetrics.get_instance()
        metrics.record_source_failed("source-1", "FETCH_TIMEOUT")
        metrics.record_source_failed("source-1", "PARSE_ERROR")
        metrics.record_source_failed("source-2", "FETCH_TIMEOUT")

        count = metrics.get_failed_count_for_source("source-1")
        assert count == 2

    def test_reset_clears_counters(self) -> None:
        """Reset clears all counters."""
        metrics = StatusMetrics.get_instance()
        metrics.record_source_failed("source-1", "FETCH_TIMEOUT")
        metrics.record_source_cannot_confirm("source-2")

        metrics.reset()

        assert len(metrics.get_sources_failed_total()) == 0
        assert len(metrics.get_sources_cannot_confirm_total()) == 0

    def test_empty_metrics_returns_empty_dicts(self) -> None:
        """Empty metrics return empty dicts."""
        metrics = StatusMetrics.get_instance()
        assert metrics.get_sources_failed_total() == {}
        assert metrics.get_sources_cannot_confirm_total() == {}

    def test_failed_count_for_unknown_source_is_zero(self) -> None:
        """Failed count for unknown source is zero."""
        metrics = StatusMetrics.get_instance()
        assert metrics.get_failed_count_for_source("unknown") == 0
