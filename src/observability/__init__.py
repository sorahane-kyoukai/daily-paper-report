"""Compatibility shims for observability imports."""

from src.features.observability import ConfigMetrics, configure_logging, get_logger


__all__ = ["ConfigMetrics", "configure_logging", "get_logger"]
