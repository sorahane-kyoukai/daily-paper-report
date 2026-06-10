"""Unit tests for evidence capture."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.features.evidence.capture import (
    ArtifactInfo,
    ArtifactManifest,
    EvidenceCapture,
    EvidenceWriteError,
)
from src.features.evidence.metrics import EvidenceMetrics
from src.features.evidence.state_machine import EvidenceState


class TestArtifactInfo:
    """Tests for ArtifactInfo dataclass."""

    def test_creates_valid_artifact(self) -> None:
        """Should create a valid ArtifactInfo."""
        artifact = ArtifactInfo(
            path="/path/to/file.md",
            checksum="abc123",
            bytes_written=1024,
            artifact_type="md",
        )
        assert artifact.path == "/path/to/file.md"
        assert artifact.checksum == "abc123"
        assert artifact.bytes_written == 1024
        assert artifact.artifact_type == "md"


class TestArtifactManifest:
    """Tests for ArtifactManifest dataclass."""

    def test_creates_valid_manifest(self) -> None:
        """Should create a valid manifest."""
        manifest = ArtifactManifest(
            run_id="test-run",
            git_commit="abc123",
            generated_at="2024-01-01T00:00:00Z",
        )
        assert manifest.run_id == "test-run"
        assert manifest.git_commit == "abc123"
        assert manifest.total_bytes == 0
        assert manifest.artifacts == []

    def test_add_artifact(self) -> None:
        """add_artifact should add artifact and update total bytes."""
        manifest = ArtifactManifest(
            run_id="test",
            git_commit="abc",
            generated_at="2024-01-01T00:00:00Z",
        )
        artifact = ArtifactInfo(
            path="/path/file.md",
            checksum="hash",
            bytes_written=500,
            artifact_type="md",
        )
        manifest.add_artifact(artifact)
        assert len(manifest.artifacts) == 1
        assert manifest.total_bytes == 500

    def test_add_multiple_artifacts(self) -> None:
        """Should accumulate bytes from multiple artifacts."""
        manifest = ArtifactManifest(
            run_id="test",
            git_commit="abc",
            generated_at="2024-01-01T00:00:00Z",
        )
        manifest.add_artifact(
            ArtifactInfo(
                path="/a.md", checksum="h1", bytes_written=100, artifact_type="md"
            )
        )
        manifest.add_artifact(
            ArtifactInfo(
                path="/b.json", checksum="h2", bytes_written=200, artifact_type="json"
            )
        )
        assert manifest.total_bytes == 300
        assert len(manifest.artifacts) == 2

    def test_to_dict_sorted_artifacts(self) -> None:
        """to_dict should sort artifacts by path."""
        manifest = ArtifactManifest(
            run_id="test",
            git_commit="abc",
            generated_at="2024-01-01T00:00:00Z",
        )
        manifest.add_artifact(
            ArtifactInfo(
                path="/z/file.md", checksum="h1", bytes_written=100, artifact_type="md"
            )
        )
        manifest.add_artifact(
            ArtifactInfo(
                path="/a/file.json",
                checksum="h2",
                bytes_written=200,
                artifact_type="json",
            )
        )
        d = manifest.to_dict()
        artifacts = d["artifacts"]
        assert isinstance(artifacts, list)
        assert artifacts[0]["path"] == "/a/file.json"
        assert artifacts[1]["path"] == "/z/file.md"


class TestEvidenceCapture:
    """Tests for EvidenceCapture class."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics singleton before each test."""
        EvidenceMetrics.reset()

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock EffectiveConfig."""
        config = MagicMock()
        config.summary.return_value = {
            "run_id": "test-run",
            "sources_count": 5,
            "enabled_sources_count": 4,
            "entities_count": 3,
            "topics_count": 2,
            "config_checksum": "checksum123",
            "file_checksums": {
                "sources.yaml": "hash1",
                "entities.yaml": "hash2",
            },
        }
        config.to_normalized_dict.return_value = {"normalized": "config"}
        return config

    @pytest.fixture
    def temp_base_path(self, tmp_path: Path) -> Path:
        """Create a temporary base path."""
        return tmp_path

    def test_initial_state_is_pending(self, temp_base_path: Path) -> None:
        """Evidence capture should start in PENDING state."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        assert capture.state == EvidenceState.EVIDENCE_PENDING

    def test_ensure_directories_creates_dirs(self, temp_base_path: Path) -> None:
        """ensure_directories should create required directories."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        capture.ensure_directories()
        assert (temp_base_path / "features" / "test-feature").exists()
        assert (temp_base_path / "features" / "test-feature" / "snapshots").exists()

    def test_compute_file_checksum(self, temp_base_path: Path) -> None:
        """compute_file_checksum should return correct SHA-256."""
        test_file = temp_base_path / "test.txt"
        test_file.write_text("hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()

        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        checksum = capture.compute_file_checksum(test_file)
        assert checksum == expected

    def test_write_state_md_creates_file(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """write_state_md should create STATE.md file."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        path = capture.write_state_md(config=mock_config, status="P1_DONE")
        assert path.exists()
        content = path.read_text()
        assert "# STATE.md - test-feature" in content
        assert "STATUS**: P1_DONE" in content

    def test_write_state_md_transitions_state(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """write_state_md should transition to WRITING state."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        assert capture.state == EvidenceState.EVIDENCE_PENDING
        capture.write_state_md(config=mock_config)
        # After state transition, mypy incorrectly narrows state type
        assert capture.state == EvidenceState.EVIDENCE_WRITING  # type: ignore[comparison-overlap]

    def test_write_state_md_includes_config_summary(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """write_state_md should include config summary."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        path = capture.write_state_md(config=mock_config)
        content = path.read_text()
        assert "Sources Count**: 5" in content
        assert "Config Checksum**: checksum123" in content

    def test_write_state_md_includes_db_stats(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """write_state_md should include DB stats when provided."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        db_stats = {"items": 100, "runs": 5}
        path = capture.write_state_md(config=mock_config, db_stats=db_stats)
        content = path.read_text()
        assert "Database Statistics" in content
        assert "| items | 100 |" in content

    def test_write_e2e_report_creates_file(self, temp_base_path: Path) -> None:
        """write_e2e_report should create E2E_RUN_REPORT.md file."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        path = capture.write_e2e_report(
            passed=True,
            steps_performed=["Step 1", "Step 2"],
            artifacts={"file1": "path1"},
        )
        assert path.exists()
        content = path.read_text()
        assert "# E2E Run Report - test-feature" in content
        assert "Status**: PASSED" in content

    def test_write_e2e_report_includes_steps(self, temp_base_path: Path) -> None:
        """write_e2e_report should include performed steps."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        path = capture.write_e2e_report(
            passed=True,
            steps_performed=["Run tests", "Verify output"],
            artifacts={},
        )
        content = path.read_text()
        assert "1. Run tests" in content
        assert "2. Verify output" in content

    def test_write_e2e_report_includes_cleared_data_steps(
        self, temp_base_path: Path
    ) -> None:
        """write_e2e_report should include cleared data steps when provided."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        path = capture.write_e2e_report(
            passed=True,
            steps_performed=["Run tests"],
            artifacts={},
            cleared_data_steps=["Deleted DB", "Cleared cache"],
        )
        content = path.read_text()
        assert "Cleared Data Steps" in content
        assert "1. Deleted DB" in content

    def test_finalize_transitions_to_done(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """finalize should transition to DONE on success."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        capture.write_state_md(config=mock_config)
        manifest = capture.finalize(success=True)
        assert capture.state == EvidenceState.EVIDENCE_DONE
        assert isinstance(manifest, ArtifactManifest)

    def test_finalize_transitions_to_failed(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """finalize should transition to FAILED on failure."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        capture.write_state_md(config=mock_config)
        capture.finalize(success=False)
        assert capture.state == EvidenceState.EVIDENCE_FAILED

    def test_manifest_tracks_artifacts(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """Manifest should track all written artifacts."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        capture.write_state_md(config=mock_config)
        capture.write_e2e_report(passed=True, steps_performed=[], artifacts={})
        # Should have STATE.md, E2E_RUN_REPORT.md, and snapshot
        assert len(capture.manifest.artifacts) >= 2

    def test_add_external_artifact(self, temp_base_path: Path) -> None:
        """add_external_artifact should add file to manifest."""
        test_file = temp_base_path / "external.html"
        test_file.write_text("<html>test</html>")

        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        artifact = capture.add_external_artifact(test_file, "html")
        assert artifact.artifact_type == "html"
        assert artifact.path == str(test_file)
        assert len(capture.manifest.artifacts) == 1

    def test_write_artifact_manifest(
        self, temp_base_path: Path, mock_config: MagicMock
    ) -> None:
        """write_artifact_manifest should create JSON manifest file."""
        capture = EvidenceCapture(
            feature_key="test-feature",
            run_id="test-run",
            base_path=temp_base_path,
        )
        capture.write_state_md(config=mock_config)
        manifest_path = capture.write_artifact_manifest()
        assert manifest_path.exists()
        content = json.loads(manifest_path.read_text())
        assert content["run_id"] == "test-run"
        assert "artifacts" in content


class TestEvidenceWriteError:
    """Tests for EvidenceWriteError exception."""

    def test_error_message(self) -> None:
        """Error should have descriptive message."""
        error = EvidenceWriteError("Failed to write", "/path/to/file")
        assert "Failed to write" in str(error)
        assert error.file_path == "/path/to/file"

    def test_error_without_path(self) -> None:
        """Error can be created without file path."""
        error = EvidenceWriteError("Generic error")
        assert error.file_path is None


class TestDeterministicFormatting:
    """Tests for deterministic report formatting."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics singleton before each test."""
        EvidenceMetrics.reset()

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock EffectiveConfig with deterministic values."""
        config = MagicMock()
        config.summary.return_value = {
            "run_id": "test-run",
            "sources_count": 3,
            "enabled_sources_count": 3,
            "entities_count": 2,
            "topics_count": 1,
            "config_checksum": "fixed_checksum",
            "file_checksums": {
                "a.yaml": "hash_a",
                "b.yaml": "hash_b",
            },
        }
        config.to_normalized_dict.return_value = {"key": "value"}
        return config

    def test_file_checksums_sorted(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """File checksums in STATE.md should be sorted by filename."""
        capture = EvidenceCapture(
            feature_key="test",
            run_id="run",
            base_path=tmp_path,
        )
        path = capture.write_state_md(config=mock_config)
        content = path.read_text()
        # a.yaml should appear before b.yaml
        pos_a = content.find("a.yaml")
        pos_b = content.find("b.yaml")
        assert pos_a < pos_b

    def test_artifacts_sorted_in_e2e_report(self, tmp_path: Path) -> None:
        """Artifacts in E2E report should be sorted by name."""
        capture = EvidenceCapture(
            feature_key="test",
            run_id="run",
            base_path=tmp_path,
        )
        path = capture.write_e2e_report(
            passed=True,
            steps_performed=[],
            artifacts={"z_file": "path_z", "a_file": "path_a"},
        )
        content = path.read_text()
        pos_a = content.find("a_file")
        pos_z = content.find("z_file")
        assert pos_a < pos_z
