"""Renderer metrics collection."""

from dataclasses import dataclass, field


@dataclass
class RendererMetrics:
    """Metrics for the static HTML renderer.

    Collects render_duration_ms, render_failures_total, render_bytes_total.
    """

    _render_duration_ms: float = 0.0
    _render_failures_total: int = 0
    _render_bytes_total: int = 0
    _files_generated: int = 0
    _json_render_ms: float = 0.0
    _html_render_ms: float = 0.0
    _template_durations: dict[str, float] = field(default_factory=dict)

    _instance: "RendererMetrics | None" = field(default=None, repr=False)

    @classmethod
    def get_instance(cls) -> "RendererMetrics":
        """Get or create the singleton instance.

        Returns:
            The singleton RendererMetrics instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance for testing."""
        cls._instance = None

    def record_render_duration(self, duration_ms: float) -> None:
        """Record total render duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self._render_duration_ms = duration_ms

    def record_failure(self) -> None:
        """Record a render failure."""
        self._render_failures_total += 1

    def record_bytes(self, bytes_written: int) -> None:
        """Record bytes written.

        Args:
            bytes_written: Number of bytes written.
        """
        self._render_bytes_total += bytes_written

    def record_file_generated(self) -> None:
        """Record a file was generated."""
        self._files_generated += 1

    def record_json_duration(self, duration_ms: float) -> None:
        """Record JSON rendering duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self._json_render_ms = duration_ms

    def record_html_duration(self, duration_ms: float) -> None:
        """Record HTML rendering duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self._html_render_ms = duration_ms

    def record_template_duration(self, template_name: str, duration_ms: float) -> None:
        """Record per-template rendering duration.

        Args:
            template_name: Name of the template.
            duration_ms: Duration in milliseconds.
        """
        self._template_durations[template_name] = duration_ms

    @property
    def render_duration_ms(self) -> float:
        """Get total render duration."""
        return self._render_duration_ms

    @property
    def render_failures_total(self) -> int:
        """Get total render failures."""
        return self._render_failures_total

    @property
    def render_bytes_total(self) -> int:
        """Get total bytes rendered."""
        return self._render_bytes_total

    @property
    def files_generated(self) -> int:
        """Get number of files generated."""
        return self._files_generated

    def get_summary(self) -> dict[str, object]:
        """Get metrics summary.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "render_duration_ms": self._render_duration_ms,
            "render_failures_total": self._render_failures_total,
            "render_bytes_total": self._render_bytes_total,
            "files_generated": self._files_generated,
            "json_render_ms": self._json_render_ms,
            "html_render_ms": self._html_render_ms,
            "template_durations": dict(self._template_durations),
        }
