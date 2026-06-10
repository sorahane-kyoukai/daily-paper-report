"""Compatibility shim for observability logging."""

from src.features.observability.logging import (
    bind_run_context,
    clear_run_context,
    configure_logging,
    get_logger,
)


__all__ = [
    "bind_run_context",
    "clear_run_context",
    "configure_logging",
    "get_logger",
]
