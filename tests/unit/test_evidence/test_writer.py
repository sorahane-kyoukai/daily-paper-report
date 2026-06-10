"""Tests for EvidenceWriter."""

from pathlib import Path

import pytest

from src.features.evidence.metrics import EvidenceMetrics
from src.features.evidence.writer import (
    ArtifactInfo,
    EvidenceWriteError,
    EvidenceWriter,
)


class TestArtifactInfo:
    """Tests for ArtifactInfo class."""

    def test_create_artifact_info(self) -> None:
        """Test creating an ArtifactInfo instance."""
        artifact = ArtifactInfo(
            path="features/test/STATE.md",
            checksum="a" * 64,
            bytes_written=100,
            artifact_type="md",
        )

        assert artifact.path == "features/test/STATE.md"
        assert artifact.checksum == "a" * 64
        assert artifact.bytes_written == 100
        assert artifact.artifact_type == "md"

    def test_artifact_info_slots(self) -> None:
        """Test that ArtifactInfo uses __slots__ for memory efficiency."""
        artifact = ArtifactInfo(
            path="features/test/STATE.md",
            checksum="a" * 64,
            bytes_written=100,
            artifact_type="md",
        )

        # Should not have __dict__ due to __slots__
        assert not hasattr(artifact, "__dict__")


class TestEvidenceWriteError:
    """Tests for EvidenceWriteError exception."""

    def test_error_with_message(self) -> None:
        """Test creating error with message only."""
        error = EvidenceWriteError("Test error")

        assert str(error) == "Test error"
        assert error.file_path is None

    def test_error_with_file_path(self) -> None:
        """Test creating error with file path."""
        error = EvidenceWriteError("Test error", "features/test/STATE.md")

        assert str(error) == "Test error"
        assert error.file_path == "features/test/STATE.md"


class TestEvidenceWriter:
    """Tests for EvidenceWriter class."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        EvidenceMetrics.reset()

    @pytest.fixture
    def writer(self) -> EvidenceWriter:
        """Create a writer instance."""
        metrics = EvidenceMetrics.get_instance()
        return EvidenceWriter(metrics, "test-run-1")

    def test_compute_checksum(self) -> None:
        """Test computing SHA-256 checksum."""
        checksum = EvidenceWriter.compute_checksum(b"test content")

        # SHA-256 of "test content"
        expected = "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"
        assert checksum == expected
        assert len(checksum) == 64

    def test_compute_checksum_empty(self) -> None:
        """Test computing checksum of empty content."""
        checksum = EvidenceWriter.compute_checksum(b"")

        # SHA-256 of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert checksum == expected

    def test_compute_file_checksum(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test computing checksum of a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        checksum = writer.compute_file_checksum(test_file)

        expected = "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"
        assert checksum == expected

    def test_write_safely_basic(self, writer: EvidenceWriter, tmp_path: Path) -> None:
        """Test basic safe file writing."""
        test_file = tmp_path / "test.md"
        content = "# Test\n\nSome content here."

        artifact = writer.write_safely(test_file, content, "md")

        assert test_file.exists()
        assert test_file.read_text() == content
        assert artifact.path == str(test_file)
        assert len(artifact.checksum) == 64
        assert artifact.bytes_written == len(content.encode("utf-8"))
        assert artifact.artifact_type == "md"

    def test_write_safely_records_metrics(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that writing records metrics."""
        test_file = tmp_path / "test.md"
        content = "Test content"

        writer.write_safely(test_file, content, "md")

        metrics = EvidenceMetrics.get_instance()
        assert metrics.files_written == 1
        assert metrics.evidence_bytes_total == len(content.encode("utf-8"))
        assert str(test_file) in metrics.file_checksums

    def test_write_safely_redacts_secrets(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that secrets are redacted when redact=True."""
        test_file = tmp_path / "test.md"
        content = "API key: sk-abc123def456abc123def456"

        writer.write_safely(test_file, content, "md", redact=True)

        written_content = test_file.read_text()
        assert "sk-abc123def456abc123def456" not in written_content
        assert "[REDACTED]" in written_content

    def test_write_safely_fails_on_secrets_when_redact_false(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that secrets cause failure when redact=False."""
        test_file = tmp_path / "test.md"
        content = "API key: sk-abc123def456abc123def456"

        with pytest.raises(EvidenceWriteError) as exc_info:
            writer.write_safely(test_file, content, "md", redact=False)

        assert "secrets" in str(exc_info.value).lower()
        assert exc_info.value.file_path == str(test_file)
        assert not test_file.exists()

    def test_write_safely_no_secrets_no_redaction(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that content without secrets is written as-is."""
        test_file = tmp_path / "test.md"
        content = "# Clean Content\n\nNo secrets here."

        writer.write_safely(test_file, content, "md", redact=True)

        assert test_file.read_text() == content
        assert "[REDACTED]" not in test_file.read_text()

    def test_write_safely_handles_io_error(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that IO errors are handled properly."""
        # Try to write to a non-existent directory
        test_file = tmp_path / "non_existent" / "test.md"

        with pytest.raises(EvidenceWriteError) as exc_info:
            writer.write_safely(test_file, "content", "md")

        assert "Failed to write" in str(exc_info.value)
        assert exc_info.value.file_path == str(test_file)

        # Check that failure was recorded in metrics
        metrics = EvidenceMetrics.get_instance()
        assert metrics.evidence_write_failures_total == 1

    def test_write_safely_utf8_encoding(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that content is written with UTF-8 encoding."""
        test_file = tmp_path / "test.md"
        content = "Unicode content: 日本語 🎉 émojis"

        artifact = writer.write_safely(test_file, content, "md")

        assert test_file.read_text(encoding="utf-8") == content
        assert artifact.bytes_written == len(content.encode("utf-8"))

    def test_write_safely_creates_artifact_info(
        self, writer: EvidenceWriter, tmp_path: Path
    ) -> None:
        """Test that ArtifactInfo is correctly populated."""
        test_file = tmp_path / "report.json"
        content = '{"key": "value"}'

        artifact = writer.write_safely(test_file, content, "json")

        assert artifact.path == str(test_file)
        assert artifact.artifact_type == "json"
        assert artifact.bytes_written == 16
        assert len(artifact.checksum) == 64


class TestEvidenceWriterIntegration:
    """Integration tests for EvidenceWriter."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        EvidenceMetrics.reset()

    def test_multiple_writes_accumulate_metrics(self, tmp_path: Path) -> None:
        """Test that multiple writes accumulate metrics correctly."""
        metrics = EvidenceMetrics.get_instance()
        writer = EvidenceWriter(metrics, "test-run-1")

        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"
        file3 = tmp_path / "file3.json"

        writer.write_safely(file1, "Content 1", "md")
        writer.write_safely(file2, "Content 2 is longer", "md")
        writer.write_safely(file3, '{"data": true}', "json")

        assert metrics.files_written == 3
        assert metrics.evidence_bytes_total == (
            len(b"Content 1") + len(b"Content 2 is longer") + len(b'{"data": true}')
        )
        assert len(metrics.file_checksums) == 3
