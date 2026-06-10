"""Persistence and snapshot logic for Story linker."""

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import structlog

from src.linker.models import LinkerResult, Story


logger = structlog.get_logger()


def compute_snapshot_checksum(content: bytes) -> str:
    """Compute SHA-256 checksum for snapshot content.

    Args:
        content: Raw bytes to checksum.

    Returns:
        Hex-encoded SHA-256 checksum.
    """
    return hashlib.sha256(content).hexdigest()


def stories_to_json(stories: list[Story], run_id: str) -> dict[str, object]:
    """Convert stories to JSON-serializable dictionary.

    Args:
        stories: List of stories to convert.
        run_id: Run identifier.

    Returns:
        JSON-serializable dictionary.
    """
    return {
        "version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "story_count": len(stories),
        "stories": [story.to_json_dict() for story in stories],
    }


def write_daily_json(
    stories: list[Story],
    output_dir: Path,
    run_id: str,
) -> tuple[Path, str]:
    """Write stories to daily.json with atomic semantics.

    Args:
        stories: Stories to write.
        output_dir: Output directory (e.g., public/).
        run_id: Run identifier.

    Returns:
        Tuple of (output_path, checksum).
    """
    log = logger.bind(component="linker", run_id=run_id)

    # Prepare output directory
    api_dir = output_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    output_path = api_dir / "daily.json"

    # Convert to JSON
    data = stories_to_json(stories, run_id)
    json_content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    content_bytes = json_content.encode("utf-8")

    # Compute checksum
    checksum = compute_snapshot_checksum(content_bytes)

    # Write atomically using temp file + rename
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=api_dir,
            prefix="daily_",
            suffix=".json.tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content_bytes)

        # Atomic rename
        temp_path.rename(output_path)
        temp_path = None  # Mark as successfully moved

        log.info(
            "daily_json_written",
            path=str(output_path),
            story_count=len(stories),
            bytes=len(content_bytes),
            checksum=checksum,
        )

    finally:
        # Clean up temp file if rename failed
        if temp_path and temp_path.exists():
            temp_path.unlink()

    return output_path, checksum


def write_linker_state_md(
    result: LinkerResult,
    output_path: Path,
    run_id: str,
    git_commit: str,
    daily_json_checksum: str,
) -> None:
    """Write linker state to STATE.md.

    Args:
        result: Linker result with stories and stats.
        output_path: Path to write STATE.md.
        run_id: Run identifier.
        git_commit: Git commit SHA.
        daily_json_checksum: Checksum of daily.json.
    """
    log = logger.bind(component="linker", run_id=run_id)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build content
    now = datetime.now(UTC).isoformat()

    lines = [
        "# Story Linker State",
        "",
        "## Status",
        "",
        "- FEATURE_KEY: add-story-linker-and-dedupe",
        "- STATUS: P1_DONE_DEPLOYED",
        "",
        "## Last Run",
        "",
        f"- Run ID: `{run_id}`",
        f"- Git Commit: `{git_commit}`",
        f"- Generated At: `{now}`",
        "",
        "## Statistics",
        "",
        f"- Items In: {result.items_in}",
        f"- Stories Out: {result.stories_out}",
        f"- Merges Total: {result.merges_total}",
        f"- Fallback Merges: {result.fallback_merges}",
        f"- Fallback Ratio: {result.fallback_ratio:.4f}",
        "",
        "## Artifacts",
        "",
        f"- daily.json checksum (SHA-256): `{daily_json_checksum}`",
        "",
        "## Sample Merge Rationales",
        "",
    ]

    # Add sample rationales (up to 5)
    sample_rationales = result.rationales[:5]
    if sample_rationales:
        for rationale in sample_rationales:
            lines.append(f"### Story: `{rationale.story_id}`")
            lines.append("")
            lines.append(f"- Items Merged: {rationale.items_merged}")
            lines.append(
                f"- Entity IDs: {', '.join(rationale.matched_entity_ids) or 'none'}"
            )
            lines.append(f"- Stable IDs: {rationale.matched_stable_ids or 'none'}")
            lines.append(f"- Fallback: {rationale.fallback_heuristic or 'none'}")
            lines.append(f"- Sources: {', '.join(rationale.source_ids)}")
            lines.append("")
    else:
        lines.append("No merge rationales (empty result).")
        lines.append("")

    content = "\n".join(lines)

    # Write file
    output_path.write_text(content, encoding="utf-8")

    log.info(
        "linker_state_md_written",
        path=str(output_path),
        stories_out=result.stories_out,
    )


class LinkerPersistence:
    """Handles persistence operations for the Story linker."""

    def __init__(
        self,
        run_id: str,
        output_dir: Path,
        feature_dir: Path,
        git_commit: str = "unknown",
    ) -> None:
        """Initialize persistence handler.

        Args:
            run_id: Run identifier.
            output_dir: Output directory for public files (e.g., public/).
            feature_dir: Feature directory for state files.
            git_commit: Git commit SHA.
        """
        self._run_id = run_id
        self._output_dir = output_dir
        self._feature_dir = feature_dir
        self._git_commit = git_commit
        self._log = logger.bind(component="linker", run_id=run_id)

    def persist_result(self, result: LinkerResult) -> tuple[Path, str]:
        """Persist linker result to all required locations.

        Args:
            result: Linker result to persist.

        Returns:
            Tuple of (daily_json_path, checksum).
        """
        # Write daily.json
        daily_path, checksum = write_daily_json(
            result.stories,
            self._output_dir,
            self._run_id,
        )

        # Write STATE.md
        state_path = self._feature_dir / "STATE.md"
        write_linker_state_md(
            result,
            state_path,
            self._run_id,
            self._git_commit,
            checksum,
        )

        self._log.info(
            "linker_persistence_complete",
            daily_json_path=str(daily_path),
            state_md_path=str(state_path),
            checksum=checksum,
        )

        return daily_path, checksum
