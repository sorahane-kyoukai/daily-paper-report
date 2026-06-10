"""Tests for CollectorMetrics."""

import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.collectors.errors import CollectorErrorClass
from src.collectors.metrics import CollectorMetrics


@pytest.fixture(autouse=True)
def reset_metrics() -> Generator[None]:
    """Reset singleton before and after each test."""
    CollectorMetrics.reset()
    yield
    CollectorMetrics.reset()


class TestCollectorMetricsSingleton:
    """Tests for singleton pattern."""

    def test_get_instance_returns_same_instance(self) -> None:
        """get_instance returns the same instance each time."""
        instance1 = CollectorMetrics.get_instance()
        instance2 = CollectorMetrics.get_instance()
        assert instance1 is instance2

    def test_reset_clears_singleton(self) -> None:
        """reset clears the singleton, allowing new instance creation."""
        instance1 = CollectorMetrics.get_instance()
        instance1.record_items("source1", "article", 5)
        CollectorMetrics.reset()
        instance2 = CollectorMetrics.get_instance()
        assert instance1 is not instance2
        assert instance2.total_items == 0

    def test_singleton_thread_safe(self) -> None:
        """Singleton creation is thread-safe."""
        instances: list[CollectorMetrics] = []

        def get_instance() -> None:
            instances.append(CollectorMetrics.get_instance())

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All instances should be the same object
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)


class TestCollectorMetricsRecordItems:
    """Tests for record_items method."""

    def test_record_items_increments_total(self) -> None:
        """record_items increments total_items."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 5)
        assert metrics.total_items == 5

    def test_record_items_multiple_sources(self) -> None:
        """record_items tracks items by source and kind."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 3)
        metrics.record_items("source2", "paper", 2)
        assert metrics.total_items == 5
        assert metrics.items_by_source_kind[("source1", "article")] == 3
        assert metrics.items_by_source_kind[("source2", "paper")] == 2

    def test_record_items_same_source_accumulates(self) -> None:
        """record_items accumulates for the same source/kind."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 3)
        metrics.record_items("source1", "article", 2)
        assert metrics.total_items == 5
        assert metrics.items_by_source_kind[("source1", "article")] == 5

    def test_record_items_thread_safe(self) -> None:
        """record_items is thread-safe."""
        metrics = CollectorMetrics()
        num_threads = 10
        items_per_thread = 100

        def record() -> None:
            for _ in range(items_per_thread):
                metrics.record_items("source1", "article", 1)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(record) for _ in range(num_threads)]
            for f in futures:
                f.result()

        assert metrics.total_items == num_threads * items_per_thread


class TestCollectorMetricsRecordFailure:
    """Tests for record_failure method."""

    def test_record_failure_increments_total(self) -> None:
        """record_failure increments total_failures."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        assert metrics.total_failures == 1

    def test_record_failure_tracks_by_source_error(self) -> None:
        """record_failure tracks failures by source and error class."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        metrics.record_failure("source1", CollectorErrorClass.PARSE)
        metrics.record_failure("source2", CollectorErrorClass.FETCH)
        assert metrics.total_failures == 3
        assert metrics.failures_by_source_error[("source1", "FETCH")] == 1
        assert metrics.failures_by_source_error[("source1", "PARSE")] == 1
        assert metrics.failures_by_source_error[("source2", "FETCH")] == 1

    def test_record_failure_same_source_accumulates(self) -> None:
        """record_failure accumulates for the same source/error."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        assert metrics.total_failures == 2
        assert metrics.failures_by_source_error[("source1", "FETCH")] == 2


class TestCollectorMetricsRecordDuration:
    """Tests for record_duration method."""

    def test_record_duration_stores_value(self) -> None:
        """record_duration stores the duration for a source."""
        metrics = CollectorMetrics()
        metrics.record_duration("source1", 150.5)
        assert metrics.duration_by_source["source1"] == 150.5
        assert metrics.total_sources == 1

    def test_record_duration_multiple_sources(self) -> None:
        """record_duration tracks durations for multiple sources."""
        metrics = CollectorMetrics()
        metrics.record_duration("source1", 100.0)
        metrics.record_duration("source2", 200.0)
        assert metrics.total_sources == 2
        assert metrics.duration_by_source["source1"] == 100.0
        assert metrics.duration_by_source["source2"] == 200.0

    def test_record_duration_overwrites_existing(self) -> None:
        """record_duration overwrites existing duration for same source."""
        metrics = CollectorMetrics()
        metrics.record_duration("source1", 100.0)
        metrics.record_duration("source1", 200.0)
        assert metrics.duration_by_source["source1"] == 200.0
        # total_sources still increments (each call is a run)
        assert metrics.total_sources == 2


class TestCollectorMetricsGetItems:
    """Tests for get_items_total method."""

    def test_get_items_total_all(self) -> None:
        """get_items_total returns total across all sources."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 3)
        metrics.record_items("source2", "paper", 2)
        assert metrics.get_items_total() == 5

    def test_get_items_total_by_source(self) -> None:
        """get_items_total filters by source_id."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 3)
        metrics.record_items("source1", "paper", 2)
        metrics.record_items("source2", "article", 10)
        assert metrics.get_items_total("source1") == 5
        assert metrics.get_items_total("source2") == 10

    def test_get_items_total_nonexistent_source(self) -> None:
        """get_items_total returns 0 for nonexistent source."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 3)
        assert metrics.get_items_total("nonexistent") == 0


class TestCollectorMetricsGetFailures:
    """Tests for get_failures_total method."""

    def test_get_failures_total_all(self) -> None:
        """get_failures_total returns total across all sources."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        metrics.record_failure("source2", CollectorErrorClass.PARSE)
        assert metrics.get_failures_total() == 2

    def test_get_failures_total_by_source(self) -> None:
        """get_failures_total filters by source_id."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        metrics.record_failure("source1", CollectorErrorClass.PARSE)
        metrics.record_failure("source2", CollectorErrorClass.FETCH)
        assert metrics.get_failures_total("source1") == 2
        assert metrics.get_failures_total("source2") == 1

    def test_get_failures_total_nonexistent_source(self) -> None:
        """get_failures_total returns 0 for nonexistent source."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        assert metrics.get_failures_total("nonexistent") == 0


class TestCollectorMetricsGetDuration:
    """Tests for get_duration method."""

    def test_get_duration_returns_value(self) -> None:
        """get_duration returns stored duration."""
        metrics = CollectorMetrics()
        metrics.record_duration("source1", 123.45)
        assert metrics.get_duration("source1") == 123.45

    def test_get_duration_nonexistent_returns_none(self) -> None:
        """get_duration returns None for nonexistent source."""
        metrics = CollectorMetrics()
        assert metrics.get_duration("nonexistent") is None


class TestCollectorMetricsPrometheusFormat:
    """Tests for to_prometheus_format method."""

    def test_prometheus_format_empty(self) -> None:
        """to_prometheus_format returns header lines for empty metrics."""
        metrics = CollectorMetrics()
        output = metrics.to_prometheus_format()
        assert "# HELP collector_items_total" in output
        assert "# TYPE collector_items_total counter" in output
        assert "# HELP collector_failures_total" in output
        assert "# TYPE collector_failures_total counter" in output
        assert "# HELP collector_duration_ms" in output
        assert "# TYPE collector_duration_ms gauge" in output

    def test_prometheus_format_with_items(self) -> None:
        """to_prometheus_format includes item metrics."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 5)
        output = metrics.to_prometheus_format()
        assert 'collector_items_total{source_id="source1",kind="article"} 5' in output

    def test_prometheus_format_with_failures(self) -> None:
        """to_prometheus_format includes failure metrics."""
        metrics = CollectorMetrics()
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        output = metrics.to_prometheus_format()
        assert (
            'collector_failures_total{source_id="source1",error_class="FETCH"} 1'
            in output
        )

    def test_prometheus_format_with_duration(self) -> None:
        """to_prometheus_format includes duration metrics."""
        metrics = CollectorMetrics()
        metrics.record_duration("source1", 123.456)
        output = metrics.to_prometheus_format()
        assert 'collector_duration_ms{source_id="source1"} 123.46' in output

    def test_prometheus_format_sorted(self) -> None:
        """to_prometheus_format outputs in sorted order."""
        metrics = CollectorMetrics()
        metrics.record_items("z_source", "article", 1)
        metrics.record_items("a_source", "article", 2)
        output = metrics.to_prometheus_format()
        lines = output.split("\n")
        # Find lines with source data
        item_lines = [line for line in lines if "collector_items_total{" in line]
        assert len(item_lines) == 2
        assert "a_source" in item_lines[0]
        assert "z_source" in item_lines[1]


class TestCollectorMetricsToDict:
    """Tests for to_dict method."""

    def test_to_dict_empty(self) -> None:
        """to_dict returns expected structure for empty metrics."""
        metrics = CollectorMetrics()
        result = metrics.to_dict()
        assert result == {
            "total_items": 0,
            "total_failures": 0,
            "total_sources": 0,
            "items_by_source_kind": {},
            "failures_by_source_error": {},
            "duration_by_source": {},
        }

    def test_to_dict_with_data(self) -> None:
        """to_dict returns all recorded data."""
        metrics = CollectorMetrics()
        metrics.record_items("source1", "article", 3)
        metrics.record_failure("source1", CollectorErrorClass.FETCH)
        metrics.record_duration("source1", 100.0)

        result = metrics.to_dict()
        assert result["total_items"] == 3
        assert result["total_failures"] == 1
        assert result["total_sources"] == 1
        assert result["items_by_source_kind"] == {("source1", "article"): 3}
        assert result["failures_by_source_error"] == {("source1", "FETCH"): 1}
        assert result["duration_by_source"] == {"source1": 100.0}


class TestCollectorMetricsIntegration:
    """Integration tests for CollectorMetrics."""

    def test_full_workflow(self) -> None:
        """Test a complete metrics recording workflow."""
        metrics = CollectorMetrics.get_instance()

        # Record success for source1
        metrics.record_items("source1", "article", 10)
        metrics.record_duration("source1", 500.0)

        # Record partial success for source2
        metrics.record_items("source2", "paper", 5)
        metrics.record_failure("source2", CollectorErrorClass.PARSE)
        metrics.record_duration("source2", 300.0)

        # Record failure for source3
        metrics.record_failure("source3", CollectorErrorClass.FETCH)
        metrics.record_duration("source3", 50.0)

        # Verify totals
        assert metrics.total_items == 15
        assert metrics.total_failures == 2
        assert metrics.total_sources == 3

        # Verify per-source queries
        assert metrics.get_items_total("source1") == 10
        assert metrics.get_items_total("source2") == 5
        assert metrics.get_items_total("source3") == 0
        assert metrics.get_failures_total("source1") == 0
        assert metrics.get_failures_total("source2") == 1
        assert metrics.get_failures_total("source3") == 1

        # Verify exports work
        prometheus_output = metrics.to_prometheus_format()
        assert "source1" in prometheus_output
        assert "source2" in prometheus_output
        assert "source3" in prometheus_output

        dict_output = metrics.to_dict()
        assert dict_output["total_items"] == 15
