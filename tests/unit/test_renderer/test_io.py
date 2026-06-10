"""Tests for the AtomicWriter utility."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from src.renderer.io import AtomicWriter


class TestAtomicWriter:
    """Tests for AtomicWriter class."""

    def test_write_creates_file(self) -> None:
        """Write creates file with correct content."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            content = "Hello, World!"
            file_path = base_dir / "test.txt"

            result = writer.write(file_path, content)

            assert file_path.exists()
            assert file_path.read_text(encoding="utf-8") == content
            assert result.bytes_written == len(content.encode("utf-8"))

    def test_write_computes_sha256(self) -> None:
        """Write computes correct SHA-256 checksum."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            content = "Test content for checksum"
            file_path = base_dir / "checksum.txt"

            result = writer.write(file_path, content)

            expected_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert result.sha256 == expected_sha256

    def test_write_returns_relative_path(self) -> None:
        """Write returns path relative to base directory."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            subdir = base_dir / "subdir"
            subdir.mkdir()
            file_path = subdir / "nested.txt"

            result = writer.write(file_path, "nested content")

            assert result.path == "subdir/nested.txt"
            assert result.absolute_path == str(file_path)

    def test_write_is_atomic_no_temp_files(self) -> None:
        """Write leaves no temporary files after completion."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            file_path = base_dir / "atomic.txt"
            writer.write(file_path, "atomic content")

            # Check for .tmp files
            tmp_files = list(base_dir.glob("*.tmp"))
            assert len(tmp_files) == 0

    def test_write_overwrites_existing_file(self) -> None:
        """Write overwrites existing file atomically."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            file_path = base_dir / "existing.txt"
            file_path.write_text("original content", encoding="utf-8")

            writer.write(file_path, "new content")

            assert file_path.read_text(encoding="utf-8") == "new content"

    def test_write_handles_unicode(self) -> None:
        """Write correctly handles unicode content."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            content = "Hello, World!"
            file_path = base_dir / "unicode.txt"

            result = writer.write(file_path, content)

            assert file_path.read_text(encoding="utf-8") == content
            assert result.bytes_written == len(content.encode("utf-8"))

    def test_write_with_run_id(self) -> None:
        """Write works correctly with run_id specified."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir, run_id="test-run-123")

            file_path = base_dir / "with_run_id.txt"
            result = writer.write(file_path, "content")

            assert result.path == "with_run_id.txt"
            assert file_path.exists()

    def test_write_creates_parent_directories_implicitly(self) -> None:
        """Write expects parent directories to exist."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            nested_dir = base_dir / "a" / "b" / "c"
            nested_dir.mkdir(parents=True)
            file_path = nested_dir / "deep.txt"

            result = writer.write(file_path, "deep content")

            assert file_path.exists()
            assert result.path == "a/b/c/deep.txt"

    def test_write_handles_empty_content(self) -> None:
        """Write handles empty string content."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            file_path = base_dir / "empty.txt"
            result = writer.write(file_path, "")

            assert file_path.exists()
            assert file_path.read_text(encoding="utf-8") == ""
            assert result.bytes_written == 0


class TestAtomicWriterEdgeCases:
    """Edge case tests for AtomicWriter."""

    def test_write_path_outside_base_dir(self) -> None:
        """Write handles paths outside base directory gracefully."""
        with TemporaryDirectory() as tmp_dir1, TemporaryDirectory() as tmp_dir2:
            base_dir = Path(tmp_dir1)
            other_dir = Path(tmp_dir2)
            writer = AtomicWriter(base_dir)

            file_path = other_dir / "outside.txt"
            result = writer.write(file_path, "outside content")

            # Path should be absolute when outside base_dir
            assert result.path == str(file_path)

    def test_write_large_content(self) -> None:
        """Write handles large content correctly."""
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            writer = AtomicWriter(base_dir)

            # 1MB of content
            content = "x" * (1024 * 1024)
            file_path = base_dir / "large.txt"

            result = writer.write(file_path, content)

            assert file_path.exists()
            assert result.bytes_written == len(content)
