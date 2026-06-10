"""Integration tests for evidence capture module."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.features.evidence import (
    ArtifactManifest,
    EvidenceCapture,
    EvidenceMetrics,
    EvidenceState,
    contains_secrets,
)


class TestEvidenceCaptureIntegration:
    """Integration tests for full evidence capture workflow."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics singleton before each test."""
        EvidenceMetrics.reset()

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock EffectiveConfig."""
        config = MagicMock()
        config.summary.return_value = {
            "run_id": "integration-test-run",
            "sources_count": 10,
            "enabled_sources_count": 8,
            "entities_count": 5,
            "topics_count": 3,
            "config_checksum": "integration_checksum_abc123",
            "file_checksums": {
                "sources.yaml": "src_hash_123",
                "entities.yaml": "ent_hash_456",
                "topics.yaml": "top_hash_789",
            },
        }
        config.to_normalized_dict.return_value = {
            "sources": [{"id": "source1"}, {"id": "source2"}],
            "entities": [{"id": "entity1"}],
            "topics": [{"id": "topic1"}],
        }
        return config

    def test_full_evidence_workflow(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Test complete evidence capture workflow."""
        feature_key = "test-feature-integration"

        # Create evidence capture
        capture = EvidenceCapture(
            feature_key=feature_key,
            run_id="integration-run-123",
            git_commit="abc123def",
            base_path=tmp_path,
        )

        # Initial state should be PENDING
        assert capture.state == EvidenceState.EVIDENCE_PENDING

        # Write STATE.md
        state_path = capture.write_state_md(
            config=mock_config,
            status="P1_DONE_DEPLOYED",
            validation_result="PASSED",
            db_stats={"items": 100, "runs": 5, "http_cache": 50},
            per_source_counts={"source1": 30, "source2": 70},
        )

        # State should transition to WRITING
        # After state transition, mypy incorrectly narrows state type
        assert capture.state == EvidenceState.EVIDENCE_WRITING  # type: ignore[comparison-overlap]

        # Verify STATE.md content
        assert state_path.exists()
        state_content = state_path.read_text()
        assert "integration-run-123" in state_content
        assert "P1_DONE_DEPLOYED" in state_content
        assert "Database Statistics" in state_content
        assert "| items | 100 |" in state_content
        assert "Per-Source Item Counts" in state_content

        # Write E2E report
        e2e_path = capture.write_e2e_report(
            passed=True,
            steps_performed=[
                "Clear prior evidence",
                "Run pipeline on fixtures",
                "Verify STATE.md exists",
                "Verify E2E_RUN_REPORT.md exists",
            ],
            artifacts={
                "state.sqlite": "db_checksum_123",
                "index.html": "html_checksum_456",
                "daily.json": "json_checksum_789",
            },
            notes="All tests passed successfully.",
            cleared_data_steps=[
                "Deleted features/test-feature-integration/",
                "Cleared snapshots directory",
            ],
        )

        # Verify E2E report content
        assert e2e_path.exists()
        e2e_content = e2e_path.read_text()
        assert "integration-run-123" in e2e_content
        assert "PASSED" in e2e_content
        assert "Cleared Data Steps" in e2e_content
        assert "All tests passed successfully" in e2e_content

        # Create some external artifacts
        html_file = tmp_path / "public" / "index.html"
        html_file.parent.mkdir(parents=True, exist_ok=True)
        html_file.write_text("<html><body>Test</body></html>")
        capture.add_external_artifact(html_file, "html")

        json_file = tmp_path / "public" / "api" / "daily.json"
        json_file.parent.mkdir(parents=True, exist_ok=True)
        json_file.write_text('{"top5": []}')
        capture.add_external_artifact(json_file, "json")

        # Write artifact manifest
        manifest_path = capture.write_artifact_manifest()
        assert manifest_path.exists()
        manifest_content = json.loads(manifest_path.read_text())
        assert manifest_content["run_id"] == "integration-run-123"
        assert (
            len(manifest_content["artifacts"]) >= 4
        )  # STATE, E2E, snapshot, manifest, externals

        # Finalize
        manifest = capture.finalize(success=True)
        assert capture.state == EvidenceState.EVIDENCE_DONE
        assert isinstance(manifest, ArtifactManifest)
        assert manifest.total_bytes > 0

    def test_evidence_files_have_checksums(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """All evidence files should have SHA-256 checksums tracked."""
        capture = EvidenceCapture(
            feature_key="checksum-test",
            run_id="checksum-run",
            base_path=tmp_path,
        )

        capture.write_state_md(config=mock_config)
        capture.write_e2e_report(passed=True, steps_performed=[], artifacts={})
        capture.write_artifact_manifest()

        # All artifacts should have checksums
        for artifact in capture.manifest.artifacts:
            assert artifact.checksum is not None
            assert len(artifact.checksum) == 64  # SHA-256 hex length
            # Verify checksum is valid hex
            int(artifact.checksum, 16)

    def test_evidence_files_no_secrets(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Evidence files should not contain secrets."""
        capture = EvidenceCapture(
            feature_key="no-secrets-test",
            run_id="secret-test-run",
            base_path=tmp_path,
        )

        # Write evidence with safe content
        capture.write_state_md(config=mock_config)
        capture.write_e2e_report(
            passed=True,
            steps_performed=["Test step"],
            artifacts={"file": "path"},
        )

        # Read all evidence files and verify no secrets
        feature_dir = tmp_path / "features" / "no-secrets-test"
        for evidence_file in feature_dir.glob("*.md"):
            content = evidence_file.read_text()
            assert not contains_secrets(content), f"Secrets found in {evidence_file}"

    def test_evidence_required_sections_exist(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Evidence files should contain all required sections."""
        capture = EvidenceCapture(
            feature_key="sections-test",
            run_id="sections-run",
            base_path=tmp_path,
        )

        state_path = capture.write_state_md(
            config=mock_config,
            db_stats={"items": 10},
            per_source_counts={"src1": 5},
        )
        e2e_path = capture.write_e2e_report(
            passed=True,
            steps_performed=["Step 1"],
            artifacts={"artifact1": "checksum1"},
            cleared_data_steps=["Clear step 1"],
        )

        # STATE.md required sections
        state_content = state_path.read_text()
        required_state_sections = [
            "## Status",
            "## Run Information",
            "## Configuration Summary",
            "## File Checksums",
            "## Validation Result",
            "## Artifact Manifest",
        ]
        for section in required_state_sections:
            assert section in state_content, f"Missing section: {section}"

        # E2E_RUN_REPORT.md required sections
        e2e_content = e2e_path.read_text()
        required_e2e_sections = [
            "## Summary",
            "## Cleared Data Steps",
            "## Steps Performed",
            "## Artifacts",
        ]
        for section in required_e2e_sections:
            assert section in e2e_content, f"Missing section: {section}"

    def test_idempotent_formatting(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Same input should produce same content (except timestamps)."""
        EvidenceMetrics.reset()
        capture1 = EvidenceCapture(
            feature_key="idempotent-test",
            run_id="idempotent-run",
            git_commit="same_commit",
            base_path=tmp_path / "run1",
        )
        state1 = capture1.write_state_md(config=mock_config, status="TEST_STATUS")

        EvidenceMetrics.reset()
        capture2 = EvidenceCapture(
            feature_key="idempotent-test",
            run_id="idempotent-run",
            git_commit="same_commit",
            base_path=tmp_path / "run2",
        )
        state2 = capture2.write_state_md(config=mock_config, status="TEST_STATUS")

        content1 = state1.read_text()
        content2 = state2.read_text()

        # Remove timestamp lines for comparison
        def remove_timestamps(content: str) -> str:
            lines = content.split("\n")
            filtered = [
                line
                for line in lines
                if not any(
                    x in line for x in ["Last Updated", "Started At", "Latest snapshot"]
                )
            ]
            return "\n".join(filtered)

        assert remove_timestamps(content1) == remove_timestamps(content2)

    def test_metrics_accumulated_correctly(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Metrics should accumulate correctly across writes."""
        capture = EvidenceCapture(
            feature_key="metrics-test",
            run_id="metrics-run",
            base_path=tmp_path,
        )

        capture.write_state_md(config=mock_config)
        capture.write_e2e_report(passed=True, steps_performed=[], artifacts={})

        metrics = EvidenceMetrics.get_instance()
        assert metrics.files_written >= 2
        assert metrics.evidence_bytes_total > 0
        assert metrics.evidence_write_failures_total == 0
        assert len(metrics.file_checksums) >= 2

    def test_snapshot_file_created(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Configuration snapshot should be created."""
        capture = EvidenceCapture(
            feature_key="snapshot-test",
            run_id="snapshot-run",
            base_path=tmp_path,
        )

        capture.write_state_md(config=mock_config)

        snapshots_dir = tmp_path / "features" / "snapshot-test" / "snapshots"
        snapshots = list(snapshots_dir.glob("config_snapshot_*.json"))
        assert len(snapshots) == 1

        snapshot_content = json.loads(snapshots[0].read_text())
        assert snapshot_content["run_id"] == "snapshot-run"
        assert "config" in snapshot_content
        assert "summary" in snapshot_content

    def test_failed_run_transitions_correctly(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Failed run should transition to FAILED state."""
        capture = EvidenceCapture(
            feature_key="failure-test",
            run_id="failure-run",
            base_path=tmp_path,
        )

        capture.write_state_md(config=mock_config)
        capture.finalize(success=False)

        assert capture.state == EvidenceState.EVIDENCE_FAILED

    def test_manifest_includes_all_artifact_types(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Manifest should track all artifact types correctly."""
        capture = EvidenceCapture(
            feature_key="types-test",
            run_id="types-run",
            base_path=tmp_path,
        )

        # Write different artifact types
        capture.write_state_md(config=mock_config)  # md
        capture.write_e2e_report(passed=True, steps_performed=[], artifacts={})  # md
        capture.write_artifact_manifest()  # json

        # Add external artifacts
        html_file = tmp_path / "test.html"
        html_file.write_text("<html></html>")
        capture.add_external_artifact(html_file, "html")

        sqlite_file = tmp_path / "state.sqlite"
        sqlite_file.write_bytes(b"sqlite content")
        capture.add_external_artifact(sqlite_file, "sqlite")

        # Verify artifact types
        types = [a.artifact_type for a in capture.manifest.artifacts]
        assert "md" in types
        assert "json" in types
        assert "html" in types
        assert "sqlite" in types
