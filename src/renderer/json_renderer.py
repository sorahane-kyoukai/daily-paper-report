"""JSON renderer for api/daily.json output."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

from src.features.config.schemas.entities import EntityConfig
from src.linker.models import Story
from src.ranker.models import RankerOutput
from src.renderer.io import AtomicWriter
from src.renderer.metrics import RendererMetrics
from src.renderer.models import (
    DailyDigest,
    GeneratedFile,
    RunInfo,
    SourceStatus,
)


logger = structlog.get_logger()


class JsonRenderer:
    """Renders JSON API output (api/daily.json).

    Produces deterministic JSON output with stable formatting and ordering.
    """

    def __init__(
        self,
        run_id: str,
        output_dir: Path,
        metrics: RendererMetrics | None = None,
        entity_configs: list[EntityConfig] | None = None,
        translations: dict[str, object] | None = None,
    ) -> None:
        """Initialize the JSON renderer.

        Args:
            run_id: Unique run identifier.
            output_dir: Output directory for rendered files.
            metrics: Optional metrics instance.
            entity_configs: Optional entity configurations for building entity catalog.
            translations: Optional map of story_id to TranslationEntry for zh injection.
        """
        self._run_id = run_id
        self._output_dir = output_dir
        self._metrics = metrics or RendererMetrics.get_instance()
        self._entity_configs = entity_configs or []
        self._translations = translations or {}
        self._log = logger.bind(run_id=run_id, component="renderer")
        self._writer = AtomicWriter(output_dir, run_id)

    def render(  # noqa: PLR0913
        self,
        ranker_output: RankerOutput,
        sources_status: list[SourceStatus],
        run_info: RunInfo,
        run_date: str,
        archive_dates: list[str] | None = None,
        skip_daily_json: bool = False,
    ) -> GeneratedFile:
        """Render JSON API output.

        Generates both per-date JSON (api/day/YYYY-MM-DD.json) and optionally
        the main daily.json file.

        Args:
            ranker_output: Output from the ranker.
            sources_status: Per-source status list.
            run_info: Run information.
            run_date: Date string (YYYY-MM-DD).
            archive_dates: List of available archive dates.
            skip_daily_json: If True, only writes per-date JSON, not daily.json.
                            Useful for backfill operations.

        Returns:
            GeneratedFile with path and checksum of the per-date JSON file.
        """
        start_time = time.perf_counter()

        self._log.info("json_render_started", run_date=run_date)

        # Build the digest structure
        generated_at = datetime.now(UTC).isoformat()

        score_map = ranker_output.score_map

        digest = DailyDigest(
            run_id=self._run_id,
            run_date=run_date,
            generated_at=generated_at,
            top5=[self._story_to_dict(s, score_map) for s in ranker_output.top5],
            model_releases_by_entity={
                entity: [self._story_to_dict(s, score_map) for s in stories]
                for entity, stories in sorted(
                    ranker_output.model_releases_by_entity.items()
                )
            },
            papers=[self._story_to_dict(s, score_map) for s in ranker_output.papers],
            radar=[self._story_to_dict(s, score_map) for s in ranker_output.radar],
            sources_status=[self._source_status_to_dict(s) for s in sources_status],
            run_info=self._run_info_to_dict(run_info),
            archive_dates=archive_dates or [],
            entity_catalog=self._build_entity_catalog(),
        )

        # Serialize with stable formatting
        json_content = json.dumps(
            digest.model_dump(),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )

        # Ensure api directories exist
        api_dir = self._output_dir / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        api_day_dir = api_dir / "day"
        api_day_dir.mkdir(parents=True, exist_ok=True)

        # Write per-date JSON file for archive access
        date_output_path = api_day_dir / f"{run_date}.json"
        file_info = self._writer.write(date_output_path, json_content)
        self._log.info("date_json_written", path=str(date_output_path))

        # Write daily.json (skip during backfill to preserve current day's data)
        if not skip_daily_json:
            output_path = api_dir / "daily.json"
            file_info = self._writer.write(output_path, json_content)
            self._log.info("daily_json_written", path=str(output_path))

        duration_ms = (time.perf_counter() - start_time) * 1000
        self._metrics.record_json_duration(duration_ms)
        self._metrics.record_bytes(file_info.bytes_written)
        self._metrics.record_file_generated()

        self._log.info(
            "json_render_complete",
            file_path=file_info.path,
            bytes_written=file_info.bytes_written,
            sha256=file_info.sha256,
            duration_ms=round(duration_ms, 2),
        )

        return file_info

    def _build_entity_catalog(self) -> dict[str, dict[str, str]]:
        """Build entity catalog mapping entity IDs to display details.

        Returns:
            Dictionary mapping entity ID to name and type.
        """
        return {
            entity.id: {
                "name": entity.name,
                "type": entity.entity_type.value,
            }
            for entity in self._entity_configs
        }

    def _story_to_dict(
        self,
        story: Story,
        score_map: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, object]:
        """Convert a Story to a JSON-serializable dictionary with scores.

        Injects Traditional Chinese translations (title_zh, summary_zh)
        when available from the translations map.

        Args:
            story: Story to convert.
            score_map: Optional mapping of story_id to score breakdown.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        result = story.to_json_dict()
        if score_map and story.story_id in score_map:
            result["scores"] = score_map[story.story_id]

        translation = self._translations.get(story.story_id)
        if translation is not None:
            result["title_zh"] = getattr(translation, "title_zh", None)
            result["summary_zh"] = getattr(translation, "summary_zh", None)

        return result

    def _source_status_to_dict(self, status: SourceStatus) -> dict[str, object]:
        """Convert a SourceStatus to a JSON-serializable dictionary.

        Args:
            status: SourceStatus to convert.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        return {
            "source_id": status.source_id,
            "name": status.name,
            "tier": status.tier,
            "method": status.method,
            "status": status.status.value,
            "reason_code": status.reason_code,
            "reason_text": status.reason_text,
            "remediation_hint": status.remediation_hint,
            "newest_item_date": (
                status.newest_item_date.isoformat() if status.newest_item_date else None
            ),
            "last_fetch_status_code": status.last_fetch_status_code,
            "items_new": status.items_new,
            "items_updated": status.items_updated,
            "category": status.category,
        }

    def _run_info_to_dict(self, run_info: RunInfo) -> dict[str, object]:
        """Convert RunInfo to a JSON-serializable dictionary.

        Args:
            run_info: RunInfo to convert.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        return {
            "run_id": run_info.run_id,
            "started_at": run_info.started_at.isoformat(),
            "finished_at": (
                run_info.finished_at.isoformat() if run_info.finished_at else None
            ),
            "success": run_info.success,
            "error_summary": run_info.error_summary,
            "items_total": run_info.items_total,
            "stories_total": run_info.stories_total,
        }
