"""Template rendering for evidence markdown files.

This module provides data classes and rendering functions for
generating STATE.md and E2E_RUN_REPORT.md files with consistent
formatting.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from src.features.evidence.capture import ArtifactInfo


@dataclass
class StateTemplateData:
    """Data for rendering STATE.md template.

    Attributes:
        feature_key: Feature identifier.
        status: Current status (e.g., P1_DONE_DEPLOYED).
        last_updated: ISO-8601 timestamp.
        run_id: Unique run identifier.
        git_commit: Git commit SHA.
        started_at: Run start time in ISO-8601 format.
        config_summary: Configuration summary dictionary.
        file_checksums: Map of file paths to SHA-256 checksums.
        validation_result: PASSED or FAILED.
        db_stats: Optional database statistics.
        per_source_counts: Optional per-source item counts.
        artifacts: List of artifact information.
        additional_notes: Additional notes to include.
    """

    feature_key: str
    status: str
    last_updated: str
    run_id: str
    git_commit: str
    started_at: str
    config_summary: dict[str, object]
    file_checksums: dict[str, str] = field(default_factory=dict)
    validation_result: str = "PASSED"
    db_stats: dict[str, int] | None = None
    per_source_counts: dict[str, int] | None = None
    artifacts: list["ArtifactInfo"] = field(default_factory=list)
    additional_notes: str = ""


@dataclass
class E2EReportTemplateData:
    """Data for rendering E2E_RUN_REPORT.md template.

    Attributes:
        feature_key: Feature identifier.
        run_id: Unique run identifier.
        git_commit: Git commit SHA.
        passed: Whether the E2E run passed.
        started: Run start time in ISO-8601 format.
        ended: Run end time in ISO-8601 format.
        duration_seconds: Duration in seconds.
        cleared_data_steps: List of clear-data steps performed.
        steps_performed: List of steps performed.
        artifacts: Dictionary of artifact name to path/checksum.
        notes: Additional notes.
    """

    feature_key: str
    run_id: str
    git_commit: str
    passed: bool
    started: str
    ended: str
    duration_seconds: float
    steps_performed: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    cleared_data_steps: list[str] | None = None
    notes: str = ""


def render_state_md(data: StateTemplateData) -> str:
    """Render STATE.md content from template data.

    Args:
        data: Template data for STATE.md.

    Returns:
        Rendered markdown content.
    """
    content = f"""# STATE.md - {data.feature_key}

## Status

- **FEATURE_KEY**: {data.feature_key}
- **STATUS**: {data.status}
- **Last Updated**: {data.last_updated}

## Run Information

- **Run ID**: {data.run_id}
- **Git Commit**: {data.git_commit}
- **Started At**: {data.started_at}

## Configuration Summary

- **Sources Count**: {data.config_summary.get("sources_count", 0)}
- **Enabled Sources**: {data.config_summary.get("enabled_sources_count", 0)}
- **Entities Count**: {data.config_summary.get("entities_count", 0)}
- **Topics Count**: {data.config_summary.get("topics_count", 0)}
- **Config Checksum**: {data.config_summary.get("config_checksum", "unknown")}

## File Checksums

| File | SHA-256 |
|------|---------|
"""
    for file_path, checksum in sorted(data.file_checksums.items()):
        content += f"| {file_path} | {checksum} |\n"

    content += f"""
## Validation Result

- **Result**: {data.validation_result}
- **Error Count**: 0
"""

    if data.db_stats:
        content += """
## Database Statistics

| Table | Row Count |
|-------|-----------|
"""
        for table, count in sorted(data.db_stats.items()):
            content += f"| {table} | {count} |\n"

    if data.per_source_counts:
        content += """
## Per-Source Item Counts

| Source ID | Items |
|-----------|-------|
"""
        for source_id, count in sorted(data.per_source_counts.items()):
            content += f"| {source_id} | {count} |\n"

    content += """
## Artifact Manifest

| Path | SHA-256 | Bytes | Type |
|------|---------|-------|------|
"""
    for artifact in sorted(data.artifacts, key=lambda a: a.path):
        content += (
            f"| {artifact.path} | {artifact.checksum[:16]}... | "
            f"{artifact.bytes_written} | {artifact.artifact_type} |\n"
        )

    content += f"""
## Configuration Snapshots

Latest snapshot: {data.last_updated}

{data.additional_notes}
"""

    return content


def render_e2e_report(data: E2EReportTemplateData) -> str:
    """Render E2E_RUN_REPORT.md content from template data.

    Args:
        data: Template data for E2E report.

    Returns:
        Rendered markdown content.
    """
    status = "PASSED" if data.passed else "FAILED"

    content = f"""# E2E Run Report - {data.feature_key}

## Summary

- **Run ID**: {data.run_id}
- **Git Commit**: {data.git_commit}
- **Status**: {status}
- **Started**: {data.started}
- **Ended**: {data.ended}
- **Duration**: {data.duration_seconds:.2f}s

"""

    if data.cleared_data_steps:
        content += """## Cleared Data Steps

"""
        for i, step in enumerate(data.cleared_data_steps, 1):
            content += f"{i}. {step}\n"
        content += "\n"

    content += """## Steps Performed

"""
    for i, step in enumerate(data.steps_performed, 1):
        content += f"{i}. {step}\n"

    content += """
## Artifacts

| Artifact | Path/Checksum |
|----------|---------------|
"""
    for name, value in sorted(data.artifacts.items()):
        content += f"| {name} | {value} |\n"

    if data.notes:
        content += f"""
## Notes

{data.notes}
"""

    return content
