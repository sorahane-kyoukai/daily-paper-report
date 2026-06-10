"""Structured logging configuration."""

import logging
import sys
from typing import TextIO

import structlog


def configure_logging(
    level: int = logging.INFO,
    output: TextIO = sys.stderr,
    json_format: bool = True,
) -> None:
    """Configure structured logging for the application.

    Sets up structlog with JSON output format and standard processors
    for timestamps, log levels, and context binding.

    Args:
        level: Logging level (default: INFO).
        output: Output stream (default: stderr).
        json_format: Whether to use JSON format (default: True).
    """
    # Configure structlog
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(sort_keys=True),
            ]
        )
    else:
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(colors=True),
            ]
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=output),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=output,
        level=level,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a bound logger instance.

    Args:
        name: Optional logger name.

    Returns:
        Bound logger instance.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_run_context(run_id: str) -> None:
    """Bind run context to all subsequent log messages.

    Args:
        run_id: Unique run identifier.
    """
    structlog.contextvars.bind_contextvars(run_id=run_id)


def clear_run_context() -> None:
    """Clear run context from log messages."""
    structlog.contextvars.unbind_contextvars("run_id")
