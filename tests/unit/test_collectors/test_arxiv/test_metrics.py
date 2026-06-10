"""Unit tests for arXiv metrics."""

from src.collectors.arxiv.metrics import ArxivMetrics


class TestArxivMetrics:
    """Tests for ArxivMetrics class."""

    def setup_method(self) -> None:
        """Reset metrics before each test."""
        ArxivMetrics.reset()

    def test_singleton_pattern(self) -> None:
        """Test that get_instance returns the same instance."""
        instance1 = ArxivMetrics.get_instance()
        instance2 = ArxivMetrics.get_instance()
        assert instance1 is instance2

    def test_reset_creates_new_instance(self) -> None:
        """Test that reset creates a new instance."""
        instance1 = ArxivMetrics.get_instance()
        ArxivMetrics.reset()
        instance2 = ArxivMetrics.get_instance()
        assert instance1 is not instance2

    def test_record_items_rss(self) -> None:
        """Test recording RSS items."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_items(10, "rss", "cs.AI")
        metrics.record_items(5, "rss", "cs.AI")

        assert metrics.get_items_total("rss", "cs.AI") == 15

    def test_record_items_api(self) -> None:
        """Test recording API items."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_items(20, "api")

        assert metrics.get_items_total("api") == 20

    def test_record_items_different_categories(self) -> None:
        """Test recording items from different categories."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_items(10, "rss", "cs.AI")
        metrics.record_items(15, "rss", "cs.LG")

        assert metrics.get_items_total("rss", "cs.AI") == 10
        assert metrics.get_items_total("rss", "cs.LG") == 15

    def test_record_deduped(self) -> None:
        """Test recording deduplicated items."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_deduped(5)
        metrics.record_deduped(3)

        assert metrics.get_deduped_total() == 8

    def test_record_api_latency(self) -> None:
        """Test recording API latency."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_api_latency(100.0)
        metrics.record_api_latency(200.0)
        metrics.record_api_latency(150.0)

        stats = metrics.get_api_latency_stats()
        assert stats["count"] == 3.0
        assert stats["p50"] == 150.0

    def test_record_error(self) -> None:
        """Test recording errors."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_error("timeout")
        metrics.record_error("timeout")
        metrics.record_error("malformed_atom")

        snapshot = metrics.get_snapshot()
        # TypedDict provides type-safe access - no isinstance check needed
        assert snapshot["errors_by_type"]["timeout"] == 2
        assert snapshot["errors_by_type"]["malformed_atom"] == 1

    def test_get_snapshot(self) -> None:
        """Test getting a snapshot of all metrics."""
        metrics = ArxivMetrics.get_instance()
        metrics.record_items(10, "rss", "cs.AI")
        metrics.record_items(5, "api")
        metrics.record_deduped(3)
        metrics.record_api_latency(100.0)
        metrics.record_error("timeout")

        snapshot = metrics.get_snapshot()

        assert "items_by_mode_category" in snapshot
        assert "deduped_total" in snapshot
        assert "api_latency" in snapshot
        assert "errors_by_type" in snapshot
        assert snapshot["deduped_total"] == 3

    def test_empty_latency_stats(self) -> None:
        """Test latency stats when no samples recorded."""
        metrics = ArxivMetrics.get_instance()
        stats = metrics.get_api_latency_stats()

        assert stats["count"] == 0
        assert stats["p50"] == 0.0
        assert stats["p90"] == 0.0
        assert stats["p99"] == 0.0

    def test_items_total_unknown_key(self) -> None:
        """Test getting items for unknown mode/category."""
        metrics = ArxivMetrics.get_instance()
        assert metrics.get_items_total("unknown", "unknown") == 0
