"""Tests for evidence template rendering."""

from src.features.evidence.template import (
    E2EReportTemplateData,
    StateTemplateData,
    render_e2e_report,
    render_state_md,
)
from src.features.evidence.writer import ArtifactInfo


class TestStateTemplateData:
    """Tests for StateTemplateData dataclass."""

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_IN_PROGRESS",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123",
            started_at="2026-01-16T00:00:00Z",
            config_summary={"sources_count": 0},
        )

        assert data.file_checksums == {}
        assert data.validation_result == "PASSED"
        assert data.db_stats is None
        assert data.per_source_counts is None
        assert data.artifacts == []
        assert data.additional_notes == ""

    def test_all_fields(self) -> None:
        """Test StateTemplateData with all fields."""
        artifact = ArtifactInfo(
            path="features/test/STATE.md",
            checksum="a" * 64,
            bytes_written=100,
            artifact_type="md",
        )
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_DONE_DEPLOYED",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123def",
            started_at="2026-01-15T23:00:00Z",
            config_summary={
                "sources_count": 5,
                "enabled_sources_count": 3,
                "entities_count": 10,
                "topics_count": 2,
                "config_checksum": "xyz789",
            },
            file_checksums={"config.yaml": "checksum123"},
            validation_result="PASSED",
            db_stats={"items": 100, "runs": 5},
            per_source_counts={"source1": 50, "source2": 50},
            artifacts=[artifact],
            additional_notes="Test notes",
        )

        assert data.feature_key == "test-feature"
        assert data.status == "P1_DONE_DEPLOYED"
        assert data.db_stats == {"items": 100, "runs": 5}
        assert len(data.artifacts) == 1


class TestE2EReportTemplateData:
    """Tests for E2EReportTemplateData dataclass."""

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
        )

        assert data.steps_performed == []
        assert data.artifacts == {}
        assert data.cleared_data_steps is None
        assert data.notes == ""

    def test_all_fields(self) -> None:
        """Test E2EReportTemplateData with all fields."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=False,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
            steps_performed=["Step 1", "Step 2"],
            artifacts={"artifact1": "checksum1"},
            cleared_data_steps=["Clear step 1"],
            notes="Test notes",
        )

        assert data.passed is False
        assert len(data.steps_performed) == 2
        assert data.cleared_data_steps == ["Clear step 1"]


class TestRenderStateMd:
    """Tests for render_state_md function."""

    def test_render_minimal(self) -> None:
        """Test rendering with minimal data."""
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_IN_PROGRESS",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123",
            started_at="2026-01-16T00:00:00Z",
            config_summary={
                "sources_count": 0,
                "enabled_sources_count": 0,
                "entities_count": 0,
                "topics_count": 0,
                "config_checksum": "test",
            },
        )

        content = render_state_md(data)

        assert "# STATE.md - test-feature" in content
        assert "**FEATURE_KEY**: test-feature" in content
        assert "**STATUS**: P1_IN_PROGRESS" in content
        assert "**Run ID**: test-run-1" in content
        assert "**Git Commit**: abc123" in content
        assert "## Configuration Summary" in content
        assert "## Validation Result" in content
        assert "## Artifact Manifest" in content

    def test_render_with_db_stats(self) -> None:
        """Test rendering with database statistics."""
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_DONE_DEPLOYED",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123",
            started_at="2026-01-16T00:00:00Z",
            config_summary={"sources_count": 0},
            db_stats={"items": 100, "runs": 5},
        )

        content = render_state_md(data)

        assert "## Database Statistics" in content
        assert "| items | 100 |" in content
        assert "| runs | 5 |" in content

    def test_render_with_per_source_counts(self) -> None:
        """Test rendering with per-source counts."""
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_DONE_DEPLOYED",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123",
            started_at="2026-01-16T00:00:00Z",
            config_summary={"sources_count": 0},
            per_source_counts={"source1": 50, "source2": 30},
        )

        content = render_state_md(data)

        assert "## Per-Source Item Counts" in content
        assert "| source1 | 50 |" in content
        assert "| source2 | 30 |" in content

    def test_render_with_artifacts(self) -> None:
        """Test rendering with artifacts in manifest."""
        artifact = ArtifactInfo(
            path="features/test/STATE.md",
            checksum="a" * 64,
            bytes_written=100,
            artifact_type="md",
        )
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_DONE_DEPLOYED",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123",
            started_at="2026-01-16T00:00:00Z",
            config_summary={"sources_count": 0},
            artifacts=[artifact],
        )

        content = render_state_md(data)

        assert "## Artifact Manifest" in content
        assert "features/test/STATE.md" in content
        assert "aaaaaaaaaaaaaaaa..." in content  # Truncated checksum
        assert "100" in content  # bytes_written

    def test_render_with_file_checksums(self) -> None:
        """Test rendering with file checksums."""
        data = StateTemplateData(
            feature_key="test-feature",
            status="P1_DONE_DEPLOYED",
            last_updated="2026-01-16T00:00:00Z",
            run_id="test-run-1",
            git_commit="abc123",
            started_at="2026-01-16T00:00:00Z",
            config_summary={"sources_count": 0},
            file_checksums={
                "config.yaml": "checksum123",
                "sources.yaml": "checksum456",
            },
        )

        content = render_state_md(data)

        assert "## File Checksums" in content
        assert "| config.yaml | checksum123 |" in content
        assert "| sources.yaml | checksum456 |" in content


class TestRenderE2EReport:
    """Tests for render_e2e_report function."""

    def test_render_minimal_passed(self) -> None:
        """Test rendering minimal passing report."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
        )

        content = render_e2e_report(data)

        assert "# E2E Run Report - test-feature" in content
        assert "**Status**: PASSED" in content
        assert "**Duration**: 3600.00s" in content
        assert "## Steps Performed" in content
        assert "## Artifacts" in content

    def test_render_minimal_failed(self) -> None:
        """Test rendering minimal failing report."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=False,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
        )

        content = render_e2e_report(data)

        assert "**Status**: FAILED" in content

    def test_render_with_steps(self) -> None:
        """Test rendering with steps performed."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
            steps_performed=["Run tests", "Check coverage", "Build docs"],
        )

        content = render_e2e_report(data)

        assert "1. Run tests" in content
        assert "2. Check coverage" in content
        assert "3. Build docs" in content

    def test_render_with_cleared_data_steps(self) -> None:
        """Test rendering with cleared data steps."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
            cleared_data_steps=["Clear cache", "Reset database"],
        )

        content = render_e2e_report(data)

        assert "## Cleared Data Steps" in content
        assert "1. Clear cache" in content
        assert "2. Reset database" in content

    def test_render_with_artifacts(self) -> None:
        """Test rendering with artifacts."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
            artifacts={"report.html": "/path/to/report.html"},
        )

        content = render_e2e_report(data)

        assert "## Artifacts" in content
        assert "| report.html | /path/to/report.html |" in content

    def test_render_with_notes(self) -> None:
        """Test rendering with notes."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
            notes="These are test notes.\nWith multiple lines.",
        )

        content = render_e2e_report(data)

        assert "## Notes" in content
        assert "These are test notes." in content
        assert "With multiple lines." in content

    def test_render_no_notes_section_when_empty(self) -> None:
        """Test that Notes section is not rendered when notes is empty."""
        data = E2EReportTemplateData(
            feature_key="test-feature",
            run_id="test-run-1",
            git_commit="abc123",
            passed=True,
            started="2026-01-16T00:00:00Z",
            ended="2026-01-16T01:00:00Z",
            duration_seconds=3600.0,
            notes="",
        )

        content = render_e2e_report(data)

        assert "## Notes" not in content
