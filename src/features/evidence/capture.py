"""Evidence capture for configuration snapshots and reports."""

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from src.features.evidence.metrics import EvidenceMetrics
from src.features.evidence.state_machine import EvidenceState, EvidenceStateMachine
from src.features.evidence.template import (
    E2EReportTemplateData,
    StateTemplateData,
    render_e2e_report,
    render_state_md,
)
from src.features.evidence.writer import (
    ArtifactInfo,
    EvidenceWriteError,
    EvidenceWriter,
)


if TYPE_CHECKING:
    from src.features.config.effective import EffectiveConfig

logger = structlog.get_logger()

# Re-export for backward compatibility
__all__ = ["ArtifactInfo", "ArtifactManifest", "EvidenceCapture", "EvidenceWriteError"]


@dataclass
class ArtifactManifest:
    """Manifest of all generated artifacts for a run.

    Attributes:
        run_id: Unique run identifier.
        git_commit: Git commit SHA.
        generated_at: ISO-8601 timestamp of manifest generation.
        artifacts: List of artifact information.
        total_bytes: Total bytes across all artifacts.
    """

    run_id: str
    git_commit: str
    generated_at: str
    artifacts: list[ArtifactInfo] = field(default_factory=list)
    total_bytes: int = 0

    def add_artifact(self, artifact: ArtifactInfo) -> None:
        """Add an artifact to the manifest.

        Args:
            artifact: Artifact information to add.
        """
        self.artifacts.append(artifact)
        self.total_bytes += artifact.bytes_written

    def to_dict(self) -> dict[str, object]:
        """Convert manifest to dictionary.

        Returns:
            Dictionary representation with sorted keys.
        """
        return {
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "generated_at": self.generated_at,
            "total_bytes": self.total_bytes,
            "artifacts": [
                {
                    "path": a.path,
                    "checksum": a.checksum,
                    "bytes_written": a.bytes_written,
                    "artifact_type": a.artifact_type,
                }
                for a in sorted(self.artifacts, key=lambda x: x.path)
            ],
        }


class EvidenceCapture:
    """Captures and persists evidence artifacts.

    Responsible for writing STATE.md, E2E_RUN_REPORT.md, and
    configuration snapshots. Uses a state machine to enforce
    proper state transitions and tracks metrics.
    """

    def __init__(
        self,
        feature_key: str,
        run_id: str,
        git_commit: str = "unknown",
        base_path: Path | None = None,
    ) -> None:
        """Initialize evidence capture.

        Args:
            feature_key: Feature key for directory path.
            run_id: Unique run identifier.
            git_commit: Git commit SHA.
            base_path: Base path for features directory.
        """
        self._feature_key = feature_key
        self._run_id = run_id
        self._git_commit = git_commit
        self._base_path = base_path or Path.cwd()
        self._feature_dir = self._base_path / "features" / feature_key
        self._snapshots_dir = self._feature_dir / "snapshots"
        self._start_time = datetime.now(UTC)
        self._state_machine = EvidenceStateMachine(run_id)
        self._metrics = EvidenceMetrics.get_instance()
        self._writer = EvidenceWriter(self._metrics, run_id)
        self._manifest = ArtifactManifest(
            run_id=run_id,
            git_commit=git_commit,
            generated_at=datetime.now(UTC).isoformat(),
        )

    @property
    def state(self) -> EvidenceState:
        """Get current evidence state."""
        return self._state_machine.state

    @property
    def manifest(self) -> ArtifactManifest:
        """Get the artifact manifest."""
        return self._manifest

    def __enter__(self) -> "EvidenceCapture":
        """Enter context manager.

        Returns:
            Self for use in with statement.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit context manager, finalizing evidence capture.

        If no exception occurred, finalizes with success=True.
        If an exception occurred, finalizes with success=False.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        if exc_type is None:
            self.finalize(success=True)
        else:
            self.finalize(success=False)

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self._feature_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)

    def compute_file_checksum(self, file_path: Path) -> str:
        """Compute SHA-256 checksum of a file.

        Args:
            file_path: Path to the file.

        Returns:
            Hex-encoded SHA-256 checksum.
        """
        return self._writer.compute_file_checksum(file_path)

    def _write_file_safely(
        self,
        file_path: Path,
        content: str,
        artifact_type: str,
        redact: bool = True,
    ) -> ArtifactInfo:
        """Write content to file with safety checks.

        Delegates to EvidenceWriter for actual writing.

        Args:
            file_path: Path to write to.
            content: Content to write.
            artifact_type: Type of artifact for manifest.
            redact: Whether to check for and redact secrets.

        Returns:
            ArtifactInfo for the written file.

        Raises:
            EvidenceWriteError: If content contains secrets and redact is False,
                or if writing fails.
        """
        artifact = self._writer.write_safely(file_path, content, artifact_type, redact)
        self._manifest.add_artifact(artifact)
        return artifact

    def write_state_md(  # noqa: PLR0913
        self,
        config: "EffectiveConfig",
        status: str = "P1_IN_PROGRESS",
        validation_result: str = "PASSED",
        additional_notes: str = "",
        db_stats: dict[str, int] | None = None,
        per_source_counts: dict[str, int] | None = None,
    ) -> Path:
        """Write or update STATE.md with configuration snapshot.

        Args:
            config: Effective configuration.
            status: Current STATUS value.
            validation_result: PASSED or FAILED.
            additional_notes: Additional notes to include.
            db_stats: Optional database statistics.
            per_source_counts: Optional per-source item counts.

        Returns:
            Path to the written STATE.md file.

        Raises:
            EvidenceWriteError: If writing fails.
        """
        start_time = time.time()
        log = logger.bind(
            run_id=self._run_id,
            component="evidence",
            file_path=str(self._feature_dir / "STATE.md"),
        )

        # Transition to WRITING state if pending
        if self._state_machine.is_pending():
            self._state_machine.transition(EvidenceState.EVIDENCE_WRITING)

        try:
            self.ensure_directories()

            summary = config.summary()
            now = datetime.now(UTC).isoformat()

            # Extract file checksums from summary
            file_checksums_raw = summary.get("file_checksums", {})
            file_checksums: dict[str, str] = {}
            if isinstance(file_checksums_raw, dict):
                file_checksums = {str(k): str(v) for k, v in file_checksums_raw.items()}

            # Build template data
            template_data = StateTemplateData(
                feature_key=self._feature_key,
                status=status,
                last_updated=now,
                run_id=self._run_id,
                git_commit=self._git_commit,
                started_at=self._start_time.isoformat(),
                config_summary=dict(summary),
                file_checksums=file_checksums,
                validation_result=validation_result,
                db_stats=db_stats,
                per_source_counts=per_source_counts,
                artifacts=list(self._manifest.artifacts),
                additional_notes=additional_notes,
            )

            content = render_state_md(template_data)

            state_path = self._feature_dir / "STATE.md"
            self._write_file_safely(state_path, content, "md")

            # Also write the snapshot
            self._write_snapshot(config)

            duration_ms = (time.time() - start_time) * 1000
            self._metrics.record_write_duration(duration_ms)

            log.info(
                "state_md_written",
                duration_ms=round(duration_ms, 2),
            )

            return state_path

        except Exception as e:
            self._state_machine.transition(EvidenceState.EVIDENCE_FAILED)
            self._metrics.record_write_failure()
            log.exception("state_md_write_failed", error=str(e))
            raise

    def _write_snapshot(self, config: "EffectiveConfig") -> Path:
        """Write configuration snapshot to snapshots directory.

        Args:
            config: Effective configuration.

        Returns:
            Path to the snapshot file.
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        snapshot_path = self._snapshots_dir / f"config_snapshot_{timestamp}.json"

        snapshot_data = {
            "run_id": self._run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "git_commit": self._git_commit,
            "config": config.to_normalized_dict(),
            "summary": config.summary(),
        }

        content = json.dumps(snapshot_data, sort_keys=True, indent=2)
        self._write_file_safely(snapshot_path, content, "json")

        # Prune old snapshots (keep latest 30)
        self._prune_snapshots(keep=30)

        return snapshot_path

    def _prune_snapshots(self, keep: int = 30) -> None:
        """Prune old snapshots, keeping only the latest N.

        Args:
            keep: Number of snapshots to keep.
        """
        snapshots = sorted(
            self._snapshots_dir.glob("config_snapshot_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for snapshot in snapshots[keep:]:
            snapshot.unlink()
            logger.debug("snapshot_pruned", file_path=str(snapshot))

    def write_e2e_report(
        self,
        passed: bool,
        steps_performed: list[str],
        artifacts: dict[str, str],
        notes: str = "",
        cleared_data_steps: list[str] | None = None,
    ) -> Path:
        """Write E2E run report.

        Args:
            passed: Whether E2E passed.
            steps_performed: List of steps performed.
            artifacts: Dictionary of artifact name to path/checksum.
            notes: Additional notes.
            cleared_data_steps: List of clear-data steps performed.

        Returns:
            Path to the report file.

        Raises:
            EvidenceWriteError: If writing fails.
        """
        start_time = time.time()
        log = logger.bind(
            run_id=self._run_id,
            component="evidence",
            file_path=str(self._feature_dir / "E2E_RUN_REPORT.md"),
        )

        # Transition to WRITING state if pending
        if self._state_machine.is_pending():
            self._state_machine.transition(EvidenceState.EVIDENCE_WRITING)

        try:
            self.ensure_directories()

            end_time = datetime.now(UTC)

            # Build template data
            template_data = E2EReportTemplateData(
                feature_key=self._feature_key,
                run_id=self._run_id,
                git_commit=self._git_commit,
                passed=passed,
                started=self._start_time.isoformat(),
                ended=end_time.isoformat(),
                duration_seconds=(end_time - self._start_time).total_seconds(),
                steps_performed=steps_performed,
                artifacts=artifacts,
                cleared_data_steps=cleared_data_steps,
                notes=notes,
            )

            content = render_e2e_report(template_data)

            report_path = self._feature_dir / "E2E_RUN_REPORT.md"
            artifact = self._write_file_safely(report_path, content, "md")

            duration_ms = (time.time() - start_time) * 1000

            log.info(
                "e2e_report_written",
                bytes_written=artifact.bytes_written,
                sha256=artifact.checksum,
                passed=passed,
                duration_ms=round(duration_ms, 2),
            )

            return report_path

        except Exception as e:
            self._state_machine.transition(EvidenceState.EVIDENCE_FAILED)
            self._metrics.record_write_failure()
            log.exception("e2e_report_write_failed", error=str(e))
            raise

    def finalize(self, success: bool = True) -> ArtifactManifest:
        """Finalize evidence capture and transition to terminal state.

        Args:
            success: Whether the overall capture succeeded.

        Returns:
            The artifact manifest.

        Raises:
            EvidenceWriteError: If finalization fails.
        """
        log = logger.bind(run_id=self._run_id, component="evidence")

        try:
            if success:
                if self._state_machine.is_writing():
                    self._state_machine.transition(EvidenceState.EVIDENCE_DONE)
                log.info(
                    "evidence_capture_complete",
                    artifacts_count=len(self._manifest.artifacts),
                    total_bytes=self._manifest.total_bytes,
                )
            else:
                if not self._state_machine.is_failed():
                    self._state_machine.transition(EvidenceState.EVIDENCE_FAILED)
                log.warning(
                    "evidence_capture_failed",
                    artifacts_count=len(self._manifest.artifacts),
                )

            return self._manifest

        except Exception as e:
            self._state_machine.transition(EvidenceState.EVIDENCE_FAILED)
            log.exception("evidence_finalize_failed", error=str(e))
            raise EvidenceWriteError(f"Failed to finalize evidence: {e}") from e

    def write_artifact_manifest(self) -> Path:
        """Write the artifact manifest to a JSON file.

        Returns:
            Path to the manifest file.
        """
        manifest_path = self._feature_dir / "artifact_manifest.json"
        content = json.dumps(self._manifest.to_dict(), sort_keys=True, indent=2)
        self._write_file_safely(manifest_path, content, "json")
        return manifest_path

    def add_external_artifact(
        self,
        file_path: Path,
        artifact_type: str,
    ) -> ArtifactInfo:
        """Add an external artifact to the manifest.

        Use this for artifacts generated outside of EvidenceCapture
        (e.g., HTML files, SQLite databases).

        Args:
            file_path: Path to the existing artifact.
            artifact_type: Type of artifact (html, json, sqlite).

        Returns:
            ArtifactInfo for the artifact.
        """
        checksum = self.compute_file_checksum(file_path)
        bytes_written = file_path.stat().st_size

        artifact = ArtifactInfo(
            path=str(file_path),
            checksum=checksum,
            bytes_written=bytes_written,
            artifact_type=artifact_type,
        )

        self._manifest.add_artifact(artifact)
        self._metrics.record_file_written(str(file_path), checksum)

        logger.bind(run_id=self._run_id, component="evidence").info(
            "external_artifact_added",
            file_path=str(file_path),
            sha256=checksum,
            bytes=bytes_written,
            artifact_type=artifact_type,
        )

        return artifact
