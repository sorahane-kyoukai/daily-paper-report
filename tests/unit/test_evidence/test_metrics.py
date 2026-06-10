"""Unit tests for evidence metrics."""

import pytest

from src.features.evidence.metrics import EvidenceMetrics


class TestEvidenceMetrics:
    """Tests for EvidenceMetrics class."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics singleton before each test."""
        EvidenceMetrics.reset()

    def test_singleton_pattern(self) -> None:
        """get_instance should return same instance."""
        m1 = EvidenceMetrics.get_instance()
        m2 = EvidenceMetrics.get_instance()
        assert m1 is m2

    def test_reset_creates_new_instance(self) -> None:
        """reset should create a new instance."""
        m1 = EvidenceMetrics.get_instance()
        EvidenceMetrics.reset()
        m2 = EvidenceMetrics.get_instance()
        assert m1 is not m2

    def test_initial_values(self) -> None:
        """Initial metric values should be zero."""
        m = EvidenceMetrics.get_instance()
        assert m.evidence_write_failures_total == 0
        assert m.evidence_bytes_total == 0
        assert m.evidence_write_duration_ms == 0.0
        assert m.files_written == 0
        assert m.file_checksums == {}

    def test_record_write_failure(self) -> None:
        """record_write_failure should increment counter."""
        m = EvidenceMetrics.get_instance()
        m.record_write_failure()
        assert m.evidence_write_failures_total == 1
        m.record_write_failure()
        assert m.evidence_write_failures_total == 2

    def test_record_bytes_written(self) -> None:
        """record_bytes_written should accumulate bytes."""
        m = EvidenceMetrics.get_instance()
        m.record_bytes_written(100)
        assert m.evidence_bytes_total == 100
        m.record_bytes_written(250)
        assert m.evidence_bytes_total == 350

    def test_record_write_duration(self) -> None:
        """record_write_duration should set duration."""
        m = EvidenceMetrics.get_instance()
        m.record_write_duration(123.45)
        assert m.evidence_write_duration_ms == 123.45

    def test_record_file_written(self) -> None:
        """record_file_written should track file and checksum."""
        m = EvidenceMetrics.get_instance()
        m.record_file_written("/path/to/file.md", "abc123")
        assert m.files_written == 1
        assert m.file_checksums["/path/to/file.md"] == "abc123"

    def test_record_multiple_files(self) -> None:
        """Should track multiple files."""
        m = EvidenceMetrics.get_instance()
        m.record_file_written("/path/file1.md", "hash1")
        m.record_file_written("/path/file2.json", "hash2")
        assert m.files_written == 2
        assert len(m.file_checksums) == 2

    def test_to_dict(self) -> None:
        """to_dict should return all metrics."""
        m = EvidenceMetrics.get_instance()
        m.record_write_failure()
        m.record_bytes_written(500)
        m.record_write_duration(50.0)
        m.record_file_written("/path/file.md", "hash123")

        d = m.to_dict()
        assert d["evidence_write_failures_total"] == 1
        assert d["evidence_bytes_total"] == 500
        assert d["evidence_write_duration_ms"] == 50.0
        assert d["files_written"] == 1
        assert d["file_checksums"] == {"/path/file.md": "hash123"}

    def test_to_dict_returns_copy_of_checksums(self) -> None:
        """to_dict should return a copy of file_checksums."""
        m = EvidenceMetrics.get_instance()
        m.record_file_written("/path/file.md", "hash123")
        d = m.to_dict()
        # Modify returned dict
        checksums = d["file_checksums"]
        if isinstance(checksums, dict):
            checksums["new_file"] = "new_hash"
        # Original should be unchanged
        assert "new_file" not in m.file_checksums
