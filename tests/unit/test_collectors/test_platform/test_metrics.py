"""Unit tests for platform metrics."""

from typing import Any

from src.collectors.platform.constants import (
    PLATFORM_GITHUB,
    PLATFORM_HUGGINGFACE,
    PLATFORM_OPENREVIEW,
)
from src.collectors.platform.metrics import PlatformMetrics


class TestPlatformMetrics:
    """Tests for PlatformMetrics."""

    def setup_method(self) -> None:
        """Reset metrics before each test."""
        PlatformMetrics.reset()

    def test_singleton(self) -> None:
        """Test metrics is a singleton."""
        m1 = PlatformMetrics.get_instance()
        m2 = PlatformMetrics.get_instance()
        assert m1 is m2

    def test_reset(self) -> None:
        """Test reset creates new instance."""
        m1 = PlatformMetrics.get_instance()
        m1.record_api_call(PLATFORM_GITHUB)

        PlatformMetrics.reset()
        m2 = PlatformMetrics.get_instance()

        assert m1 is not m2
        assert m2.get_api_calls_total(PLATFORM_GITHUB) == 0

    def test_record_api_call(self) -> None:
        """Test recording API calls."""
        metrics = PlatformMetrics.get_instance()

        metrics.record_api_call(PLATFORM_GITHUB)
        metrics.record_api_call(PLATFORM_GITHUB)
        metrics.record_api_call(PLATFORM_HUGGINGFACE)

        assert metrics.get_api_calls_total(PLATFORM_GITHUB) == 2
        assert metrics.get_api_calls_total(PLATFORM_HUGGINGFACE) == 1
        assert metrics.get_api_calls_total(PLATFORM_OPENREVIEW) == 0
        assert metrics.get_api_calls_total() == 3

    def test_record_rate_limit_event(self) -> None:
        """Test recording rate limit events."""
        metrics = PlatformMetrics.get_instance()

        metrics.record_rate_limit_event(PLATFORM_GITHUB)
        metrics.record_rate_limit_event(PLATFORM_OPENREVIEW)
        metrics.record_rate_limit_event(PLATFORM_OPENREVIEW)

        assert metrics.get_rate_limit_events_total(PLATFORM_GITHUB) == 1
        assert metrics.get_rate_limit_events_total(PLATFORM_OPENREVIEW) == 2
        assert metrics.get_rate_limit_events_total() == 3

    def test_record_items(self) -> None:
        """Test recording items."""
        metrics = PlatformMetrics.get_instance()

        metrics.record_items(PLATFORM_GITHUB, 10)
        metrics.record_items(PLATFORM_HUGGINGFACE, 20)

        data = metrics.to_dict()
        items_by_platform: dict[str, Any] = data["items_by_platform"]  # type: ignore[assignment]
        assert items_by_platform[PLATFORM_GITHUB] == 10
        assert items_by_platform[PLATFORM_HUGGINGFACE] == 20

    def test_record_error(self) -> None:
        """Test recording errors."""
        metrics = PlatformMetrics.get_instance()

        metrics.record_error(PLATFORM_GITHUB, "auth")
        metrics.record_error(PLATFORM_GITHUB, "fetch")
        metrics.record_error(PLATFORM_HUGGINGFACE, "auth")

        data = metrics.to_dict()
        errors_by_platform: dict[str, Any] = data["errors_by_platform"]  # type: ignore[assignment]
        assert errors_by_platform["github:auth"] == 1
        assert errors_by_platform["github:fetch"] == 1
        assert errors_by_platform["huggingface:auth"] == 1

    def test_to_prometheus_format(self) -> None:
        """Test Prometheus format export."""
        metrics = PlatformMetrics.get_instance()

        metrics.record_api_call(PLATFORM_GITHUB)
        metrics.record_api_call(PLATFORM_HUGGINGFACE)
        metrics.record_rate_limit_event(PLATFORM_GITHUB)

        prom = metrics.to_prometheus_format()

        assert "github_api_calls_total 1" in prom
        assert "hf_api_calls_total 1" in prom
        assert "openreview_api_calls_total 0" in prom
        assert 'platform_rate_limit_events_total{platform="github"} 1' in prom

    def test_to_dict(self) -> None:
        """Test dictionary export."""
        metrics = PlatformMetrics.get_instance()

        metrics.record_api_call(PLATFORM_GITHUB)
        metrics.record_items(PLATFORM_GITHUB, 5)

        data = metrics.to_dict()

        assert "api_calls" in data
        assert "rate_limit_events" in data
        assert "items_by_platform" in data
        assert "errors_by_platform" in data
