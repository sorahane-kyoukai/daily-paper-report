"""Metrics collection for configuration validation."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class ConfigMetrics:
    """Metrics for configuration validation.

    Attributes:
        config_validation_duration_ms: Time taken to validate configs.
        config_validation_errors_total: Total validation errors.
        files_loaded: Number of config files loaded.
    """

    config_validation_duration_ms: float = 0.0
    config_validation_errors_total: int = 0
    files_loaded: int = 0

    _instance: ClassVar["ConfigMetrics | None"] = None

    @classmethod
    def get_instance(cls) -> "ConfigMetrics":
        """Get singleton metrics instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset metrics (primarily for testing)."""
        cls._instance = None

    def record_validation_duration(self, duration_ms: float) -> None:
        """Record validation duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self.config_validation_duration_ms = duration_ms

    def record_validation_error(self) -> None:
        """Record a validation error."""
        self.config_validation_errors_total += 1

    def record_file_loaded(self) -> None:
        """Record a file loaded."""
        self.files_loaded += 1

    def to_dict(self) -> dict[str, float | int]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "config_validation_duration_ms": self.config_validation_duration_ms,
            "config_validation_errors_total": self.config_validation_errors_total,
            "files_loaded": self.files_loaded,
        }
