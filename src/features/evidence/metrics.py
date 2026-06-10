"""Metrics collection for evidence capture."""

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class EvidenceMetrics:
    """Metrics for evidence capture operations.

    Attributes:
        evidence_write_failures_total: Total number of evidence write failures.
        evidence_bytes_total: Total bytes written across all evidence files.
        evidence_write_duration_ms: Duration of evidence writing in milliseconds.
        files_written: Number of evidence files written.
    """

    evidence_write_failures_total: int = 0
    evidence_bytes_total: int = 0
    evidence_write_duration_ms: float = 0.0
    files_written: int = 0
    file_checksums: dict[str, str] = field(default_factory=dict)

    _instance: ClassVar["EvidenceMetrics | None"] = None

    @classmethod
    def get_instance(cls) -> "EvidenceMetrics":
        """Get singleton metrics instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset metrics (primarily for testing)."""
        cls._instance = None

    def record_write_failure(self) -> None:
        """Record an evidence write failure."""
        self.evidence_write_failures_total += 1

    def record_bytes_written(self, bytes_count: int) -> None:
        """Record bytes written.

        Args:
            bytes_count: Number of bytes written.
        """
        self.evidence_bytes_total += bytes_count

    def record_write_duration(self, duration_ms: float) -> None:
        """Record write duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self.evidence_write_duration_ms = duration_ms

    def record_file_written(self, file_path: str, checksum: str) -> None:
        """Record a file written with its checksum.

        Args:
            file_path: Path to the file written.
            checksum: SHA-256 checksum of the file.
        """
        self.files_written += 1
        self.file_checksums[file_path] = checksum

    def to_dict(self) -> dict[str, float | int | dict[str, str]]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "evidence_write_failures_total": self.evidence_write_failures_total,
            "evidence_bytes_total": self.evidence_bytes_total,
            "evidence_write_duration_ms": self.evidence_write_duration_ms,
            "files_written": self.files_written,
            "file_checksums": self.file_checksums.copy(),
        }
