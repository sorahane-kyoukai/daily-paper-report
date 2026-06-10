"""Safe file writing utilities for evidence capture.

This module provides the EvidenceWriter class that handles
file writing with checksum computation, secret redaction,
and metrics tracking.
"""

import hashlib
from pathlib import Path

import structlog

from src.features.evidence.metrics import EvidenceMetrics
from src.features.evidence.redact import contains_secrets, redact_content


logger = structlog.get_logger()


class EvidenceWriteError(Exception):
    """Raised when evidence writing fails.

    Attributes:
        file_path: Path to the file that failed to write.
    """

    def __init__(self, message: str, file_path: str | None = None) -> None:
        """Initialize the error.

        Args:
            message: Error message.
            file_path: Path to the file that failed to write.
        """
        self.file_path = file_path
        super().__init__(message)


class ArtifactInfo:
    """Information about a generated artifact.

    Attributes:
        path: Path to the artifact file.
        checksum: SHA-256 checksum of the file content.
        bytes_written: Number of bytes written.
        artifact_type: Type of artifact (html, json, sqlite, md).
    """

    __slots__ = ("path", "checksum", "bytes_written", "artifact_type")

    def __init__(
        self,
        path: str,
        checksum: str,
        bytes_written: int,
        artifact_type: str,
    ) -> None:
        """Initialize artifact info.

        Args:
            path: Path to the artifact file.
            checksum: SHA-256 checksum.
            bytes_written: Number of bytes written.
            artifact_type: Type of artifact.
        """
        self.path = path
        self.checksum = checksum
        self.bytes_written = bytes_written
        self.artifact_type = artifact_type


class EvidenceWriter:
    """Handles safe file writing with checksum and redaction.

    This class is responsible for:
    - Computing SHA-256 checksums
    - Detecting and redacting secrets
    - Writing files safely with proper error handling
    - Recording metrics for written files
    """

    def __init__(self, metrics: EvidenceMetrics, run_id: str) -> None:
        """Initialize the evidence writer.

        Args:
            metrics: Metrics instance for tracking writes.
            run_id: Unique run identifier for logging.
        """
        self._metrics = metrics
        self._run_id = run_id
        self._log = logger.bind(run_id=run_id, component="evidence")

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        """Compute SHA-256 checksum of content.

        Args:
            content: Bytes to compute checksum for.

        Returns:
            Hex-encoded SHA-256 checksum (64 characters).
        """
        return hashlib.sha256(content).hexdigest()

    def compute_file_checksum(self, file_path: Path) -> str:
        """Compute SHA-256 checksum of a file.

        Args:
            file_path: Path to the file.

        Returns:
            Hex-encoded SHA-256 checksum.
        """
        content = file_path.read_bytes()
        return self.compute_checksum(content)

    def write_safely(
        self,
        file_path: Path,
        content: str,
        artifact_type: str,
        redact: bool = True,
    ) -> ArtifactInfo:
        """Write content to file with safety checks.

        Performs the following:
        1. Checks content for secrets
        2. Optionally redacts secrets
        3. Computes SHA-256 checksum
        4. Writes file to disk
        5. Records metrics

        Args:
            file_path: Path to write to.
            content: Content to write.
            artifact_type: Type of artifact for manifest.
            redact: Whether to redact secrets (True) or fail (False).

        Returns:
            ArtifactInfo for the written file.

        Raises:
            EvidenceWriteError: If content contains secrets and redact is False,
                or if writing fails.
        """
        log = self._log.bind(file_path=str(file_path))

        # Check for secrets
        if contains_secrets(content):
            if redact:
                content = redact_content(content)
                log.warning("content_redacted", reason="secrets_detected")
            else:
                log.error("secrets_detected", file_path=str(file_path))
                raise EvidenceWriteError(
                    f"Content contains secrets: {file_path}", str(file_path)
                )

        try:
            content_bytes = content.encode("utf-8")
            checksum = self.compute_checksum(content_bytes)

            file_path.write_text(content)

            bytes_written = len(content_bytes)
            artifact = ArtifactInfo(
                path=str(file_path),
                checksum=checksum,
                bytes_written=bytes_written,
                artifact_type=artifact_type,
            )

            self._metrics.record_bytes_written(bytes_written)
            self._metrics.record_file_written(str(file_path), checksum)

            log.info(
                "evidence_file_written",
                bytes_written=bytes_written,
                sha256=checksum,
            )

            return artifact

        except OSError as e:
            log.exception("evidence_write_failed", error=str(e))
            self._metrics.record_write_failure()
            raise EvidenceWriteError(
                f"Failed to write {file_path}: {e}", str(file_path)
            ) from e
