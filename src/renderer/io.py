"""I/O utilities for the renderer module.

Provides atomic file writing to prevent partial writes and ensure data integrity.
"""

import hashlib
from pathlib import Path

import structlog

from src.renderer.models import GeneratedFile


logger = structlog.get_logger()


class AtomicWriter:
    """Provides atomic file writing operations.

    Writes content to a temporary file first, then renames to the final path.
    This ensures that readers never see partially written files.
    """

    def __init__(self, base_dir: Path, run_id: str | None = None) -> None:
        """Initialize the atomic writer.

        Args:
            base_dir: Base directory for relative path calculation.
            run_id: Optional run ID for logging context.
        """
        self._base_dir = base_dir
        self._log = logger.bind(component="atomic_writer")
        if run_id:
            self._log = self._log.bind(run_id=run_id)

    def write(self, path: Path, content: str) -> GeneratedFile:
        """Write content to file with atomic semantics.

        Writes to a temporary file first, then renames to final path.
        This guarantees that readers see either the complete old file
        or the complete new file, never a partial write.

        Args:
            path: Target file path (absolute).
            content: Content to write (will be encoded as UTF-8).

        Returns:
            GeneratedFile with path, checksum, and size information.
        """
        content_bytes = content.encode("utf-8")
        sha256 = hashlib.sha256(content_bytes).hexdigest()

        # Write to temp file then rename for atomicity
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.rename(path)

        # Calculate relative path for manifest
        try:
            relative_path = str(path.relative_to(self._base_dir))
        except ValueError:
            relative_path = str(path)

        self._log.debug(
            "file_written",
            path=relative_path,
            bytes=len(content_bytes),
            sha256=sha256[:12],
        )

        return GeneratedFile(
            path=relative_path,
            absolute_path=str(path),
            bytes_written=len(content_bytes),
            sha256=sha256,
        )
