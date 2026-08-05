"""CLI commands for the digest system."""

import logging
import subprocess
import sys
import uuid
import zoneinfo
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import click
import structlog


if TYPE_CHECKING:
    from collections.abc import Callable

    from src.collectors.runner import RunnerResult
    from src.features.config.effective import EffectiveConfig
    from src.features.llm.protocols import LlmClient
    from src.features.store.models import Run
    from src.linker.models import LinkerResult, Story
    from src.ranker.models import RankerResult
    from src.reports import ReportDigest, ReportMetadata

from src.collectors.runner import CollectorRunner
from src.features.config.constants import (
    COMPONENT_CLI,
    FEATURE_KEY,
    STATUS_P1_DONE,
    VALIDATION_PASSED,
)
from src.features.config.error_hints import format_validation_error
from src.features.config.loader import ConfigLoader
from src.features.config.state_machine import ConfigState
from src.features.evidence.capture import EvidenceCapture
from src.features.fetch.client import HttpFetcher
from src.features.fetch.config import FetchConfig
from src.features.status import StatusComputer
from src.features.store.store import StateStore
from src.linker import StoryLinker
from src.observability.logging import bind_run_context, configure_logging
from src.ranker import StoryRanker
from src.renderer import RunInfo, SourceStatus, StaticRenderer


logger = structlog.get_logger()

# Default daily digest display window (24 hours)
# Can be overridden via --lookback parameter to show papers from longer periods.
DEFAULT_DISPLAY_HOURS = 24
LLM_CACHE_VERSION = 2


# Type aliases for phase results
CollectionPhaseResult = tuple[
    "CollectorRunner",  # runner
    object,  # runner_result (RunnerResult)
]


def get_git_commit() -> str:
    """Get current git commit SHA."""
    try:
        result = subprocess.run(  # noqa: S603, S607
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


@dataclass
class RunOptions:
    """Options for the run command."""

    config_path: Path
    entities_path: Path
    topics_path: Path
    state_path: Path
    output_dir: Path
    timezone: str
    json_logs: bool
    verbose: bool
    dry_run: bool = False
    lookback_hours: int = 24
    source_max_items: int | None = None
    retention_days: int = 90
    skip_translation: bool = False
    target_date: str | None = None


def _setup_logging_and_context(
    options: RunOptions, run_id: str
) -> structlog.typing.FilteringBoundLogger:
    """Set up logging and return bound logger.

    Args:
        options: Run options.
        run_id: Unique run identifier.

    Returns:
        Bound logger with run context.
    """
    log_level = logging.DEBUG if options.verbose else logging.INFO
    configure_logging(level=log_level, json_format=options.json_logs)
    bind_run_context(run_id)

    log = logger.bind(
        run_id=run_id,
        component=COMPONENT_CLI,
        command="run",
        dry_run=options.dry_run,
    )

    log.info(
        "digest_run_started",
        config_path=str(options.config_path),
        entities_path=str(options.entities_path),
        topics_path=str(options.topics_path),
        state_path=str(options.state_path),
        output_dir=str(options.output_dir),
        timezone=options.timezone,
        target_date=options.target_date,
    )

    return log  # type: ignore[no-any-return]


def _validate_timezone(
    timezone: str, log: structlog.typing.FilteringBoundLogger
) -> None:
    """Validate timezone format, exit on failure.

    Args:
        timezone: Timezone string to validate.
        log: Logger for error reporting.
    """
    try:
        zoneinfo.ZoneInfo(timezone)
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        log.warning("invalid_timezone", timezone=timezone)
        click.echo(f"Error: Invalid timezone '{timezone}'", err=True)
        sys.exit(1)


def _load_configuration(
    options: RunOptions, run_id: str, log: structlog.typing.FilteringBoundLogger
) -> "EffectiveConfig":
    """Load and validate configuration.

    Args:
        options: Run options with paths.
        run_id: Run identifier.
        log: Logger instance.

    Returns:
        Validated effective configuration.
    """
    from src.features.config.effective import EffectiveConfig

    loader = ConfigLoader(run_id=run_id)

    try:
        effective_config: EffectiveConfig = loader.load(
            sources_path=options.config_path,
            entities_path=options.entities_path,
            topics_path=options.topics_path,
        )
    except Exception as e:
        log.warning(
            "config_load_failed",
            error=str(e),
            validation_errors=loader.validation_errors,
        )

        click.echo("Configuration validation failed:", err=True)
        for error in loader.validation_errors:
            formatted = format_validation_error(
                location=error["loc"],
                message=error["msg"],
                error_type=error.get("type", "unknown"),
                include_hint=True,
            )
            click.echo(f"  - {formatted}", err=True)

        sys.exit(1)

    if loader.state != ConfigState.READY:
        log.error("unexpected_state", state=loader.state.name)
        sys.exit(1)

    log.info(
        "config_validated",
        sources_count=len(effective_config.sources.sources),
        entities_count=len(effective_config.entities.entities),
        topics_count=len(effective_config.topics.topics),
        config_checksum=effective_config.compute_checksum(),
    )

    return effective_config


def _run_collection_phase(  # noqa: PLR0913
    store: StateStore,
    effective_config: "EffectiveConfig",
    strip_params: list[str],
    run_id: str,
    log: structlog.typing.FilteringBoundLogger,
    lookback_hours: int = 24,
    source_max_items: int | None = None,
) -> "RunnerResult":
    """Execute the collection phase.

    Args:
        store: State store instance.
        effective_config: Validated configuration.
        strip_params: URL parameters to strip.
        run_id: Run identifier.
        log: Logger instance.
        lookback_hours: Number of hours to look back for items.
        source_max_items: Optional per-source max_items override.

    Returns:
        CollectorRunner result.
    """
    log.info("phase_started", phase="collection", lookback_hours=lookback_hours)

    fetch_config = FetchConfig()
    http_client = HttpFetcher(
        config=fetch_config,
        store=store,
        run_id=run_id,
    )

    collector_runner = CollectorRunner(
        store=store,
        http_client=http_client,
        run_id=run_id,
        max_workers=1,
        strip_params=strip_params,
        lookback_hours=lookback_hours,
        max_items_per_source=source_max_items,
    )

    runner_result = collector_runner.run(
        sources=effective_config.sources.sources,
        now=datetime.now(UTC),
    )

    log.info(
        "collection_complete",
        total_items=runner_result.total_items,
        total_new=runner_result.total_new,
        sources_succeeded=runner_result.sources_succeeded,
        sources_failed=runner_result.sources_failed,
    )

    return runner_result


def _failed_arxiv_sources(
    runner_result: "RunnerResult",
    effective_config: "EffectiveConfig",
) -> list[str]:
    """Return enabled arXiv API sources that did not complete successfully."""
    from src.features.config.schemas.base import SourceMethod

    arxiv_source_ids = {
        source.id
        for source in effective_config.sources.sources
        if source.enabled and source.method == SourceMethod.ARXIV_API
    }
    failed_sources: list[str] = []

    for source_id in arxiv_source_ids:
        source_result = runner_result.source_results.get(source_id)
        if source_result is None or not source_result.result.success:
            failed_sources.append(source_id)

    return sorted(failed_sources)


def _run_linking_phase(  # noqa: PLR0913
    store: StateStore,
    effective_config: "EffectiveConfig",
    run_record: "Run",
    lookback_hours: int,
    run_id: str,
    log: structlog.typing.FilteringBoundLogger,
) -> "LinkerResult":
    """Execute the linking phase.

    Args:
        store: State store instance.
        effective_config: Validated configuration.
        run_record: Current run record.
        lookback_hours: Hours to look back for items.
        run_id: Run identifier.
        log: Logger instance.

    Returns:
        Linker result with stories.
    """
    from src.linker.models import LinkerResult

    log.info("phase_started", phase="linking")

    published_cutoff = datetime.fromtimestamp(
        run_record.started_at.timestamp() - (lookback_hours * 60 * 60),
        tz=UTC,
    )

    all_items = store.get_items_published_since(
        published_since=published_cutoff,
        first_seen_since=None,
    )

    log.info(
        "items_filtered_by_published_at",
        lookback_hours=lookback_hours,
        published_cutoff=published_cutoff.isoformat(),
        items_after_filter=len(all_items),
    )

    linker = StoryLinker(
        run_id=run_id,
        entities_config=effective_config.entities,
        topics_config=effective_config.topics,
    )

    linker_result: LinkerResult = linker.link_items(all_items)

    log.info(
        "linking_complete",
        stories_count=len(linker_result.stories),
        items_in=linker_result.items_in,
    )

    return linker_result


def _run_llm_phase(
    linker_result: "LinkerResult",
    effective_config: "EffectiveConfig",
    run_id: str,  # noqa: ARG001
    log: structlog.typing.FilteringBoundLogger,
    output_dir: Path | None = None,
) -> dict[str, float]:
    """Execute the optional LLM relevance evaluation phase.

    Skips gracefully if DEEPSEEK_API_KEY is not configured or
    if any error occurs during evaluation. Saves versioned scorecards to the
    output directory for offline analysis when output_dir is given.

    Args:
        linker_result: Result from linking phase.
        effective_config: Validated configuration.
        run_id: Run identifier.
        log: Logger instance.
        output_dir: Optional output directory for caching scores.

    Returns:
        Dictionary mapping story_id to LLM relevance score (0.0-1.0).
        Empty dict when LLM phase is skipped or fails.
    """
    import json as _json

    from src.settings.app import get_settings

    # Load cached scores from previous run first so we can reuse them even
    # when LLM credentials are not available.
    cached_scores: dict[str, float] = {}
    cached_entries: dict[str, dict[str, object]] = {}
    if output_dir:
        cache_path = output_dir / "api" / "llm_scores.json"
        if cache_path.exists():
            try:
                raw_cache = _json.loads(cache_path.read_text())
                if (
                    isinstance(raw_cache, dict)
                    and raw_cache.get("version") == LLM_CACHE_VERSION
                ):
                    raw_entries = raw_cache.get("entries", {})
                    if isinstance(raw_entries, dict):
                        cached_entries = {
                            str(key): value
                            for key, value in raw_entries.items()
                            if isinstance(value, dict)
                        }
                        cached_scores = {
                            key: float(score)
                            for key, value in cached_entries.items()
                            if isinstance((score := value.get("score")), int | float)
                        }
                elif isinstance(raw_cache, dict):
                    cached_scores = {
                        str(key): float(value)
                        for key, value in raw_cache.items()
                        if isinstance(value, int | float)
                    }
                log.info(
                    "llm_cache_loaded",
                    cached_count=len(cached_scores),
                    path=str(cache_path),
                )
            except (ValueError, OSError):
                log.warning("llm_cache_load_failed", path=str(cache_path))

    settings = get_settings()
    if not _has_llm_credentials(settings):
        log.info(
            "llm_phase_skipped",
            reason="no_llm_credentials",
            cached_count=len(cached_scores),
        )
        return cached_scores

    log.info("phase_started", phase="llm_relevance")

    try:
        from src.features.fulltext import FullTextService
        from src.features.llm.processor import LlmRelevanceProcessor
        from src.features.llm.prompts import CURRENT_SCORING_PROMPT_VERSION

        client = _create_configured_llm_client(settings)
        cache_dir = Path(
            settings.fulltext_cache_dir
            or ((output_dir or Path("public")).parent / ".cache" / "fulltext")
        )
        documents = FullTextService(cache_dir).load_for_stories(linker_result.stories)
        processor = LlmRelevanceProcessor(
            client=client,
            topics=list(effective_config.topics.topics),
            documents=documents,
        )

        # Filter to only uncached stories
        all_stories = linker_result.stories
        uncached_stories = []
        for story in all_stories:
            document = documents.get(story.story_id)
            cached = cached_entries.get(story.story_id, {})
            is_current = bool(
                document
                and cached.get("fulltext_sha256") == document.sha256
                and cached.get("prompt_version") == CURRENT_SCORING_PROMPT_VERSION
                and cached.get("model") == settings.deepseek_model
            )
            if not is_current:
                uncached_stories.append(story)

        if uncached_stories:
            log.info(
                "llm_evaluating_uncached",
                total=len(all_stories),
                cached=len(all_stories) - len(uncached_stories),
                to_evaluate=len(uncached_stories),
            )
            phase_result = processor.evaluate_stories(uncached_stories)
        else:
            log.info(
                "llm_all_cached",
                total=len(all_stories),
                cached=len(cached_scores),
            )
            phase_result = processor.evaluate_stories([])

        log.info(
            "llm_phase_complete",
            evaluated=phase_result.stories_evaluated,
            skipped=phase_result.stories_skipped,
            api_calls=phase_result.api_calls_made,
            errors=len(phase_result.errors),
        )

        # Merge cached + new scores
        scores = {**cached_scores, **phase_result.scores}

        # Cache merged scores for future runs
        if output_dir and scores:
            cache_path = output_dir / "api" / "llm_scores.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            new_entries = dict(cached_entries)
            for item in phase_result.results:
                new_entries[item.story_id] = {
                    "score": item.relevance_score,
                    "components": item.component_scores,
                    "confidence": item.confidence,
                    "rationale": item.rationale,
                    "topics": item.topics_matched,
                    "evidence": item.evidence,
                    "fulltext_status": item.fulltext_status,
                    "fulltext_sha256": item.fulltext_sha256,
                    "token_usage": item.token_usage,
                    "prompt_version": CURRENT_SCORING_PROMPT_VERSION,
                    "model": settings.deepseek_model,
                }
            cache_path.write_text(
                _json.dumps(
                    {
                        "version": LLM_CACHE_VERSION,
                        "model": settings.deepseek_model,
                        "prompt_version": CURRENT_SCORING_PROMPT_VERSION,
                        "entries": new_entries,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            log.info("llm_scores_cached", path=str(cache_path), count=len(scores))

        return scores

    except Exception:
        log.warning("llm_phase_failed", exc_info=True)
        # Return cached scores as fallback if available
        if cached_scores:
            log.info("llm_using_cached_fallback", count=len(cached_scores))
            return cached_scores
        return {}


def _collect_ranker_story_dicts(
    ranker_result: "RankerResult",
) -> list[dict[str, object]]:
    """Collect deduplicated story dicts from user-visible ranker sections.

    Args:
        ranker_result: Result from ranking phase.

    Returns:
        Deduplicated list of story dicts.
    """
    return [story.to_json_dict() for story in _collect_ranker_stories(ranker_result)]


def _collect_ranker_stories(ranker_result: "RankerResult") -> list["Story"]:
    """Collect deduplicated visible Story models in display order."""
    from itertools import chain

    from src.linker.models import Story

    model_release_stories: list[Story] = list(
        chain.from_iterable(ranker_result.output.model_releases_by_entity.values())
    )
    candidates = [
        *ranker_result.output.top5,
        *ranker_result.output.papers,
        *ranker_result.output.radar,
        *model_release_stories,
    ]
    seen: set[str] = set()
    unique: list[Story] = []
    for story in candidates:
        if story.story_id not in seen:
            seen.add(story.story_id)
            unique.append(story)
    return unique


def _load_cached_translations(
    output_dir: Path,
    stories: list[dict[str, object]],
    log: structlog.typing.FilteringBoundLogger,
) -> dict[str, object]:
    """Load cached zh translations for the provided stories.

    Args:
        output_dir: Output directory containing api/translations_zh.json.
        stories: Story dictionaries with story_id fields.
        log: Logger instance.

    Returns:
        Mapping of story_id to cached TranslationEntry objects.
    """
    from src.features.translation.models import TranslationCache

    cache = TranslationCache(output_dir / "api" / "translations_zh.json")
    cache.load()

    story_ids = {
        str(story.get("story_id", "")) for story in stories if story.get("story_id")
    }
    matched: dict[str, object] = {
        sid: entry for sid, entry in cache.entries.items() if sid in story_ids
    }

    if matched:
        log.info(
            "translation_cache_used",
            cached_count=len(matched),
            requested_count=len(story_ids),
        )

    return matched


def _run_translation_phase(
    ranker_result: "RankerResult",
    run_id: str,  # noqa: ARG001
    log: structlog.typing.FilteringBoundLogger,
    output_dir: Path | None = None,
) -> dict[str, object] | None:
    """Execute the optional LLM translation phase.

    Translates ranked story titles and summaries to Traditional Chinese.
    Skips gracefully if DEEPSEEK_API_KEY is not configured or if
    any error occurs during translation.

    Args:
        ranker_result: Result from ranking phase (provides final story lists).
        run_id: Run identifier.
        log: Logger instance.
        output_dir: Optional output directory for cache file storage.

    Returns:
        Dictionary mapping story_id to TranslationEntry, or None if
        translation phase is skipped or fails.
    """
    from src.settings.app import get_settings

    if output_dir is None:
        log.info("translation_phase_skipped", reason="no_output_dir")
        return None

    visible_story_models = _collect_ranker_stories(ranker_result)
    unique_stories = [story.to_json_dict() for story in visible_story_models]
    cached_translations = _load_cached_translations(output_dir, unique_stories, log)

    settings = get_settings()
    if not _has_llm_credentials(settings):
        if cached_translations:
            log.info(
                "translation_phase_using_cached",
                reason="no_llm_credentials",
                cached_count=len(cached_translations),
            )
            return cached_translations

        log.info("translation_phase_skipped", reason="no_llm_credentials")
        return None

    log.info("phase_started", phase="translation")

    try:
        from src.features.fulltext import FullTextService
        from src.features.translation.processor import TranslationProcessor

        cache_dir = Path(
            settings.fulltext_cache_dir
            or (output_dir.parent / ".cache" / "fulltext")
        )
        documents = FullTextService(cache_dir).load_for_stories(visible_story_models)
        for story in unique_stories:
            document = documents.get(str(story.get("story_id", "")))
            if document is not None:
                story["fulltext"] = document.text
                story["fulltext_sha256"] = document.sha256
                story["fulltext_status"] = document.status.value

        client = _create_configured_llm_client(settings)
        processor = TranslationProcessor(client=client, output_dir=output_dir)

        result = processor.translate(unique_stories)

        log.info(
            "translation_phase_complete",
            translated=len(result),
            total_stories=len(unique_stories),
        )

        return result  # type: ignore[return-value]

    except Exception:
        log.warning("translation_phase_failed", exc_info=True)
        if cached_translations:
            log.info(
                "translation_phase_using_cached_fallback",
                cached_count=len(cached_translations),
            )
            return cached_translations
        return None


def _has_llm_credentials(settings: object) -> bool:
    """Return whether the required DeepSeek credential is present."""
    return bool(getattr(settings, "deepseek_api_key", None))


def _create_configured_llm_client(settings: object) -> "LlmClient":
    """Create the configured LLM client from application settings."""
    from src.features.llm.factory import create_llm_client

    return create_llm_client(
        api_key=getattr(settings, "deepseek_api_key", None),
        model=getattr(settings, "deepseek_model", "deepseek-v4-flash"),
        max_tokens=getattr(settings, "deepseek_max_tokens", 8192),
    )


def _create_report_metadata_generator(
    log: structlog.typing.FilteringBoundLogger,
) -> "Callable[[ReportDigest], ReportMetadata | None] | None":
    """Create an optional AI metadata generator for report publishing."""
    from src.reports import ReportDigest, ReportMetadata
    from src.reports.ai_metadata import generate_report_metadata
    from src.settings.app import get_settings

    settings = get_settings()
    if not _has_llm_credentials(settings):
        log.info("report_ai_metadata_skipped", reason="no_llm_credentials")
        return None

    try:
        client = _create_configured_llm_client(settings)
    except Exception:
        log.warning("report_ai_metadata_client_failed", exc_info=True)
        return None

    def _generate(report: ReportDigest) -> ReportMetadata | None:
        try:
            metadata = generate_report_metadata(client, report)
        except Exception:
            log.warning(
                "report_ai_metadata_failed",
                period_id=report.period_id,
                report_type=report.report_type,
                exc_info=True,
            )
            return None

        log.info(
            "report_ai_metadata_complete",
            period_id=report.period_id,
            report_type=report.report_type,
            has_title=bool(metadata and metadata.title),
            has_summary=bool(metadata and metadata.summary),
        )
        return metadata

    return _generate


def _run_ranking_phase(
    linker_result: "LinkerResult",
    effective_config: "EffectiveConfig",
    run_id: str,
    log: structlog.typing.FilteringBoundLogger,
    llm_scores: dict[str, float] | None = None,
) -> "RankerResult":
    """Execute the ranking phase.

    Args:
        linker_result: Result from linking phase.
        effective_config: Validated configuration.
        run_id: Run identifier.
        log: Logger instance.
        llm_scores: Pre-computed LLM relevance scores.

    Returns:
        Ranker result with scored stories.
    """
    from src.ranker.models import RankerResult

    log.info("phase_started", phase="ranking")

    ranker = StoryRanker(
        run_id=run_id,
        topics_config=effective_config.topics,
        entities_config=effective_config.entities,
        llm_scores=llm_scores,
    )

    ranker_result: RankerResult = ranker.rank_stories(linker_result.stories)

    log.info(
        "ranking_complete",
        top5_count=len(ranker_result.output.top5),
        papers_count=len(ranker_result.output.papers),
        radar_count=len(ranker_result.output.radar),
    )

    return ranker_result


def _run_rendering_phase(  # noqa: PLR0913
    ranker_result: "RankerResult",
    runner_result: "RunnerResult",
    effective_config: "EffectiveConfig",
    linker_result: "LinkerResult",
    run_record: "Run",
    options: RunOptions,
    run_id: str,
    log: structlog.typing.FilteringBoundLogger,
    translations: dict[str, object] | None = None,
) -> None:
    """Execute the rendering phase.

    Args:
        ranker_result: Result from ranking phase.
        runner_result: Result from collection phase.
        effective_config: Validated configuration.
        linker_result: Result from linking phase.
        run_record: Current run record.
        options: Run options.
        run_id: Run identifier.
        log: Logger instance.
        translations: Optional translation map (story_id -> TranslationEntry).
    """
    log.info("phase_started", phase="rendering")

    source_configs_dict = {s.id: s for s in effective_config.sources.sources}
    status_computer = StatusComputer(
        run_id=run_id,
        source_configs=source_configs_dict,
    )
    sources_status = status_computer.compute_all(runner_result)

    run_info = RunInfo(
        run_id=run_id,
        started_at=run_record.started_at,
        finished_at=datetime.now(UTC),
        items_total=runner_result.total_items,
        stories_total=len(linker_result.stories),
        success=True,
    )

    renderer = StaticRenderer(
        run_id=run_id,
        output_dir=options.output_dir,
        timezone=options.timezone,
        retention_days=options.retention_days,
        entity_configs=list(effective_config.entities.entities),
        translations=translations,
    )

    render_result = renderer.render(
        ranker_output=ranker_result.output,
        sources_status=sources_status,
        run_info=run_info,
        recent_runs=[run_info],
        target_date=options.target_date,
    )

    if render_result.success:
        log.info(
            "rendering_complete",
            files_count=len(render_result.manifest.files),
            total_bytes=render_result.manifest.total_bytes,
        )
    else:
        log.error("rendering_failed", error=render_result.error_summary)


def _write_evidence_capture(
    effective_config: "EffectiveConfig",
    run_id: str,
    log: structlog.typing.FilteringBoundLogger,
) -> None:
    """Write evidence capture file.

    Args:
        effective_config: Validated configuration.
        run_id: Run identifier.
        log: Logger instance (unused but kept for consistency).
    """
    _ = log  # Unused but kept for API consistency
    git_commit = get_git_commit()
    evidence = EvidenceCapture(
        feature_key=FEATURE_KEY,
        run_id=run_id,
        git_commit=git_commit,
    )

    evidence.write_state_md(
        config=effective_config,
        status=STATUS_P1_DONE,
        validation_result=VALIDATION_PASSED,
    )


def _execute_run(options: RunOptions) -> None:
    """Execute the run command with given options.

    Orchestrates the digest pipeline through phases:
    1. Setup and validation
    2. Collection
    3. Linking
    4. Ranking
    5. Rendering
    6. Evidence capture
    """
    run_id = str(uuid.uuid4())
    log = _setup_logging_and_context(options, run_id)
    _validate_timezone(options.timezone, log)
    effective_config = _load_configuration(options, run_id, log)

    if not options.dry_run:
        strip_params = list(effective_config.topics.dedupe.canonical_url_strip_params)

        with StateStore(
            db_path=options.state_path,
            strip_params=strip_params,
            run_id=run_id,
        ) as store:
            _execute_pipeline_phases(
                store, effective_config, strip_params, options, run_id, log
            )

        _write_evidence_capture(effective_config, run_id, log)
    else:
        log.info(
            "dry_run_skip_evidence", message="Skipping evidence capture in dry-run mode"
        )

    log.info(
        "digest_run_complete",
        state="READY",
        config_checksum=effective_config.compute_checksum(),
    )

    click.echo(f"Configuration validated successfully. Run ID: {run_id}")


def _execute_pipeline_phases(  # noqa: PLR0913
    store: StateStore,
    effective_config: "EffectiveConfig",
    strip_params: list[str],
    options: RunOptions,
    run_id: str,
    log: structlog.typing.FilteringBoundLogger,
) -> None:
    """Execute all pipeline phases within store context.

    Args:
        store: State store instance.
        effective_config: Validated configuration.
        strip_params: URL parameters to strip.
        options: Run options.
        run_id: Run identifier.
        log: Logger instance.
    """
    log.info(
        "store_connected",
        db_path=str(options.state_path),
        schema_version=store.get_schema_version(),
    )

    run_record = store.begin_run(run_id)
    log.info(
        "run_started_in_store",
        run_id=run_record.run_id,
        started_at=run_record.started_at.isoformat(),
    )

    last_success = store.get_last_successful_run_finished_at()
    if last_success:
        log.info("last_successful_run", finished_at=last_success.isoformat())
    else:
        log.info("no_previous_successful_run")

    # Phase 1: Collection
    runner_result = _run_collection_phase(
        store,
        effective_config,
        strip_params,
        run_id,
        log,
        options.lookback_hours,
        options.source_max_items,
    )

    failed_arxiv_sources = _failed_arxiv_sources(runner_result, effective_config)
    if failed_arxiv_sources:
        error_summary = "Critical arXiv coverage incomplete: " + ", ".join(
            failed_arxiv_sources
        )
        log.error(
            "critical_arxiv_coverage_incomplete",
            failed_sources=failed_arxiv_sources,
        )
        store.end_run(run_id, success=False, error_summary=error_summary)
        click.echo(f"Error: {error_summary}", err=True)
        sys.exit(1)

    # Phase 2: Linking
    # Use the same lookback_hours for linking phase to ensure daily.json
    # contains papers from the entire lookback period (e.g., 7 days with --lookback 168).
    linker_result = _run_linking_phase(
        store, effective_config, run_record, options.lookback_hours, run_id, log
    )

    # Phase 2.5: LLM Relevance (optional, skips gracefully if unconfigured)
    llm_scores = _run_llm_phase(
        linker_result,
        effective_config,
        run_id,
        log,
        output_dir=options.output_dir,
    )

    # Phase 3: Ranking
    ranker_result = _run_ranking_phase(
        linker_result, effective_config, run_id, log, llm_scores
    )

    # Phase 3.5: Translation (optional, skips gracefully if unconfigured or disabled)
    translations: dict[str, object] | None = None
    if options.skip_translation:
        log.info("translation_phase_skipped", reason="disabled_by_flag")
    else:
        translations = _run_translation_phase(
            ranker_result, run_id, log, output_dir=options.output_dir
        )

    # Phase 4: Rendering
    _run_rendering_phase(
        ranker_result,
        runner_result,
        effective_config,
        linker_result,
        run_record,
        options,
        run_id,
        log,
        translations=translations,
    )

    # Finalize run
    run_record = store.end_run(run_id, success=True)
    log.info(
        "run_finished_in_store",
        run_id=run_record.run_id,
        success=run_record.success,
        finished_at=run_record.finished_at.isoformat()
        if run_record.finished_at
        else None,
    )

    stats = store.get_stats()
    log.info(
        "store_stats",
        runs=stats["runs"],
        items=stats["items"],
        http_cache=stats["http_cache"],
    )


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """Research Report digest system CLI."""


@cli.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to sources.yaml configuration file.",
)
@click.option(
    "--entities",
    "entities_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to entities.yaml configuration file.",
)
@click.option(
    "--topics",
    "topics_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to topics.yaml configuration file.",
)
@click.option(
    "--state",
    "state_path",
    required=True,
    type=click.Path(path_type=Path),
    help="Path to SQLite state database.",
)
@click.option(
    "--out",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for generated files.",
)
@click.option(
    "--tz",
    "timezone",
    required=True,
    type=str,
    help="Timezone for date handling (e.g., Asia/Taipei).",
)
@click.option(
    "--json-logs/--no-json-logs",
    default=True,
    help="Use JSON format for logs (default: true).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate configuration without writing state or evidence.",
)
@click.option(
    "--lookback",
    "lookback_hours",
    type=int,
    default=24,
    help="Lookback window in hours for filtering items by published_at (default: 24).",
)
@click.option(
    "--source-max-items",
    "source_max_items",
    type=int,
    default=None,
    help="Per-source max_items override for this run. If omitted, use each source's configured max_items. 0 means unlimited while still using safe API fetch caps.",
)
@click.option(
    "--retention-days",
    "retention_days",
    type=int,
    default=90,
    help="Number of days to retain archive pages (default: 90).",
)
@click.option(
    "--date",
    "target_date",
    type=str,
    default=None,
    help="Target archive date to render as YYYY-MM-DD. Defaults to current UTC date.",
)
@click.option(
    "--no-translate",
    "skip_translation",
    is_flag=True,
    default=False,
    help="Skip the translation phase (saves time and tokens).",
)
def run(  # noqa: PLR0913
    config_path: Path,
    entities_path: Path,
    topics_path: Path,
    state_path: Path,
    output_dir: Path,
    timezone: str,
    json_logs: bool,
    verbose: bool,
    dry_run: bool,
    lookback_hours: int,
    source_max_items: int | None,
    retention_days: int,
    target_date: str | None,
    skip_translation: bool,
) -> None:
    """Run the digest pipeline.

    Loads and validates configuration, then executes the digest pipeline.
    Configuration validation happens before any network calls.

    Use --dry-run to validate configuration without writing any state files.
    This is useful before a manual Nano deployment.
    """
    if target_date is not None:
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            click.echo(
                f"Error: Invalid date format '{target_date}'. Use YYYY-MM-DD.",
                err=True,
            )
            sys.exit(1)

    options = RunOptions(
        config_path=config_path,
        entities_path=entities_path,
        topics_path=topics_path,
        state_path=state_path,
        output_dir=output_dir,
        timezone=timezone,
        json_logs=json_logs,
        verbose=verbose,
        dry_run=dry_run,
        lookback_hours=lookback_hours,
        source_max_items=source_max_items,
        retention_days=retention_days,
        skip_translation=skip_translation,
        target_date=target_date,
    )
    _execute_run(options)


@cli.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to sources.yaml configuration file.",
)
@click.option(
    "--entities",
    "entities_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to entities.yaml configuration file.",
)
@click.option(
    "--topics",
    "topics_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to topics.yaml configuration file.",
)
def validate(
    config_path: Path,
    entities_path: Path,
    topics_path: Path,
) -> None:
    """Validate configuration files without running the pipeline."""
    run_id = str(uuid.uuid4())
    configure_logging(json_format=False)
    bind_run_context(run_id)

    loader = ConfigLoader(run_id=run_id)

    try:
        effective_config = loader.load(
            sources_path=config_path,
            entities_path=entities_path,
            topics_path=topics_path,
        )

        click.echo("Configuration is valid!")
        click.echo(f"  Sources: {len(effective_config.sources.sources)}")
        click.echo(f"  Entities: {len(effective_config.entities.entities)}")
        click.echo(f"  Topics: {len(effective_config.topics.topics)}")
        click.echo(f"  Checksum: {effective_config.compute_checksum()}")

    except Exception:
        click.echo("Configuration validation failed:", err=True)
        for error in loader.validation_errors:
            formatted = format_validation_error(
                location=error["loc"],
                message=error["msg"],
                error_type=error.get("type", "unknown"),
                include_hint=True,
            )
            click.echo(f"  - {formatted}", err=True)
        sys.exit(1)


@cli.command("db-stats")
@click.option(
    "--state",
    "state_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SQLite state database.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output as JSON.",
)
def db_stats(state_path: Path, json_output: bool) -> None:
    """Display state database statistics.

    Shows row counts for all tables, schema version, and last successful run.
    """
    import json

    configure_logging(json_format=False)

    with StateStore(db_path=state_path) as store:
        stats = store.get_stats()
        schema_version = store.get_schema_version()
        last_success = store.get_last_successful_run_finished_at()

        if json_output:
            output = {
                "schema_version": schema_version,
                "tables": stats,
                "last_successful_run": (
                    last_success.isoformat() if last_success else None
                ),
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo("State Database Statistics")
            click.echo("=" * 40)
            click.echo(f"  Schema Version: {schema_version}")
            click.echo(
                f"  Last Successful Run: {last_success.isoformat() if last_success else 'None'}"
            )
            click.echo("")
            click.echo("Table Row Counts:")
            for table, count in sorted(stats.items()):
                click.echo(f"  {table}: {count}")


@cli.command()
@click.option(
    "--out",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for generated files.",
)
@click.option(
    "--tz",
    "timezone",
    default="UTC",
    type=str,
    help="Timezone for date display (default: UTC).",
)
@click.option(
    "--json-logs/--no-json-logs",
    default=True,
    help="Use JSON format for logs (default: true).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
def render(
    output_dir: Path,
    timezone: str,
    json_logs: bool,
    verbose: bool,
) -> None:
    """Render static HTML pages from fixture data.

    This command is primarily for testing the renderer with sample data.
    In production, rendering happens as part of the full pipeline run.
    """
    from datetime import UTC, datetime

    from src.features.config.schemas.base import LinkType
    from src.linker.models import Story, StoryLink
    from src.ranker.models import RankerOutput
    from src.renderer import RenderResult, RunInfo, StaticRenderer

    run_id = str(uuid.uuid4())

    log_level = logging.DEBUG if verbose else logging.INFO
    configure_logging(level=log_level, json_format=json_logs)
    bind_run_context(run_id)

    log = logger.bind(run_id=run_id, component=COMPONENT_CLI, command="render")
    log.info("render_started", output_dir=str(output_dir), timezone=timezone)

    # Create sample data for testing
    sample_story = Story(
        story_id="sample-story-1",
        title="Sample Story for Testing",
        primary_link=StoryLink(
            url="https://example.com/sample",
            link_type=LinkType.OFFICIAL,
            source_id="sample-source",
            tier=0,
            title="Sample Story for Testing",
        ),
        links=[
            StoryLink(
                url="https://example.com/sample",
                link_type=LinkType.OFFICIAL,
                source_id="sample-source",
                tier=0,
                title="Sample Story for Testing",
            )
        ],
        entities=["sample-entity"],
        published_at=datetime.now(UTC),
    )

    ranker_output = RankerOutput(
        top5=[sample_story],
        model_releases_by_entity={"sample-entity": [sample_story]},
        papers=[],
        radar=[sample_story],
        output_checksum="sample-checksum",
    )

    run_info = RunInfo(
        run_id=run_id,
        started_at=datetime.now(UTC),
        items_total=1,
        stories_total=1,
    )

    renderer = StaticRenderer(
        run_id=run_id,
        output_dir=output_dir,
        timezone=timezone,
    )

    result: RenderResult = renderer.render(
        ranker_output=ranker_output,
        sources_status=[],
        run_info=run_info,
        recent_runs=[run_info],
    )

    if result.success:
        log.info(
            "render_complete",
            files_count=len(result.manifest.files),
            total_bytes=result.manifest.total_bytes,
            duration_ms=round(result.manifest.duration_ms, 2),
        )
        click.echo(f"Render complete. {len(result.manifest.files)} files generated.")
        click.echo(f"Output directory: {output_dir}")
        for file_info in result.manifest.files:
            click.echo(f"  {file_info.path} ({file_info.bytes_written} bytes)")
    else:
        log.error("render_failed", error=result.error_summary)
        click.echo(f"Render failed: {result.error_summary}", err=True)
        sys.exit(1)


@cli.command("clear-archives")
@click.option(
    "--out",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory containing day archives.",
)
@click.option(
    "--json-logs/--no-json-logs",
    default=True,
    help="Use JSON format for logs (default: true).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
def clear_archives(
    output_dir: Path,
    json_logs: bool,
    verbose: bool,
) -> None:
    """Clear all day archive HTML files.

    This command removes all day/YYYY-MM-DD.html files from the output
    directory. Useful when the frontend panel design changes and you
    need to regenerate all archives with the new design.
    """
    run_id = str(uuid.uuid4())

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    configure_logging(level=log_level, json_format=json_logs)
    bind_run_context(run_id)

    log = logger.bind(
        run_id=run_id,
        component=COMPONENT_CLI,
        command="clear-archives",
    )

    day_dir = Path(output_dir) / "day"

    if not day_dir.exists():
        log.info("day_dir_not_found", path=str(day_dir))
        click.echo(f"Day archive directory does not exist: {day_dir}")
        return

    # Find and delete all HTML files in day directory
    deleted_count = 0
    for html_file in day_dir.glob("*.html"):
        try:
            html_file.unlink()
            deleted_count += 1
            log.debug("file_deleted", path=str(html_file))
        except OSError as e:
            log.warning("file_delete_failed", path=str(html_file), error=str(e))

    log.info("clear_archives_complete", deleted_count=deleted_count)
    click.echo(f"Cleared {deleted_count} day archive files from {day_dir}")


@cli.command("report")
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(["weekly", "monthly"]),
    help="Report type to generate.",
)
@click.option(
    "--out",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory containing api/day/*.json archives.",
)
@click.option(
    "--tz",
    "timezone",
    default="UTC",
    type=str,
    help="Timezone for period and publication-date bucketing.",
)
@click.option(
    "--date",
    "target_date_str",
    type=str,
    required=False,
    help="Local target date (YYYY-MM-DD). Defaults to today in --tz.",
)
@click.option(
    "--period",
    "period_id",
    type=str,
    required=False,
    help="Explicit report period: weekly YYYY-Www, monthly YYYY-MM.",
)
@click.option(
    "--previous-month",
    is_flag=True,
    default=False,
    help="For monthly reports without --period, generate the month before --date.",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum number of recommended papers.",
)
@click.option(
    "--archive-lookahead-days",
    type=int,
    default=1,
    show_default=True,
    help=(
        "Extra archive dates after the report period to scan for late-arriving "
        "papers whose published_at still falls inside the period."
    ),
)
@click.option(
    "--ai-metadata/--no-ai-metadata",
    default=True,
    help=(
        "Use the configured LLM to generate the report title and quick summary "
        "when credentials are available."
    ),
)
@click.option(
    "--json-logs/--no-json-logs",
    default=True,
    help="Use JSON format for logs (default: true).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
def report(  # noqa: PLR0913
    report_type: str,
    output_dir: Path,
    timezone: str,
    target_date_str: str | None,
    period_id: str | None,
    previous_month: bool,
    limit: int,
    archive_lookahead_days: int,
    ai_metadata: bool,
    json_logs: bool,
    verbose: bool,
) -> None:
    """Generate a weekly or monthly worth-reading paper report.

    The command aggregates already-persisted day archive JSON files under
    api/day/*.json. It does not fetch sources; when LLM credentials are present,
    it also asks the configured provider for a concise title and quick summary.
    """
    from typing import cast

    from src.reports import ReportType, build_report_from_archives

    run_id = str(uuid.uuid4())
    log_level = logging.DEBUG if verbose else logging.INFO
    configure_logging(level=log_level, json_format=json_logs)
    bind_run_context(run_id)

    log = logger.bind(
        run_id=run_id,
        component=COMPONENT_CLI,
        command="report",
        report_type=report_type,
    )

    try:
        local_tz = zoneinfo.ZoneInfo(timezone)
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        click.echo(f"Error: Invalid timezone '{timezone}'", err=True)
        sys.exit(1)

    if limit <= 0:
        click.echo("Error: --limit must be greater than 0.", err=True)
        sys.exit(1)

    if archive_lookahead_days < 0:
        click.echo(
            "Error: --archive-lookahead-days must be greater than or equal to 0.",
            err=True,
        )
        sys.exit(1)

    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            click.echo(
                f"Error: Invalid date format '{target_date_str}'. Use YYYY-MM-DD.",
                err=True,
            )
            sys.exit(1)
    else:
        target_date = datetime.now(local_tz).date()

    log.info(
        "report_generation_started",
        output_dir=str(output_dir),
        target_date=target_date.isoformat(),
        timezone=timezone,
        period_id=period_id,
        previous_month=previous_month,
        limit=limit,
        archive_lookahead_days=archive_lookahead_days,
        ai_metadata=ai_metadata,
    )

    metadata_generator = None
    if ai_metadata:
        metadata_generator = _create_report_metadata_generator(log)

    try:
        digest = build_report_from_archives(
            output_dir=output_dir,
            report_type=cast("ReportType", report_type),
            target_date=target_date,
            timezone=timezone,
            limit=limit,
            period_id=period_id,
            previous_month=previous_month,
            archive_lookahead_days=archive_lookahead_days,
            metadata_generator=metadata_generator,
        )
    except ValueError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    log.info(
        "report_generation_complete",
        period_id=digest.period_id,
        recommendations=len(digest.recommendations),
        blog_recommendations=len(digest.blog_recommendations),
        missing_dates=digest.missing_dates,
    )
    click.echo(
        f"Generated {digest.report_type} report {digest.period_id}: "
        f"{len(digest.recommendations)} paper recommendations, "
        f"{len(digest.blog_recommendations)} blog recommendations "
        f"({len(digest.missing_dates)} missing dates)."
    )


@cli.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to sources.yaml configuration file.",
)
@click.option(
    "--entities",
    "entities_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to entities.yaml configuration file.",
)
@click.option(
    "--topics",
    "topics_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to topics.yaml configuration file.",
)
@click.option(
    "--state",
    "state_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SQLite state database.",
)
@click.option(
    "--out",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for generated files.",
)
@click.option(
    "--tz",
    "timezone",
    required=True,
    type=str,
    help="Timezone for date handling (e.g., Asia/Taipei).",
)
@click.option(
    "--date",
    "target_date_str",
    type=str,
    required=True,
    help="Specific date to generate (YYYY-MM-DD format).",
)
@click.option(
    "--overwrite-existing/--skip-existing",
    "overwrite_existing",
    default=False,
    help="Overwrite existing day archives. Default skips existing files to preserve enriched historical data.",
)
@click.option(
    "--json-logs/--no-json-logs",
    default=True,
    help="Use JSON format for logs (default: true).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
def backfill(  # noqa: C901, PLR0913, PLR0915
    config_path: Path,
    entities_path: Path,
    topics_path: Path,
    state_path: Path,
    output_dir: Path,
    timezone: str,
    target_date_str: str,
    overwrite_existing: bool,
    json_logs: bool,
    verbose: bool,
) -> None:
    """Backfill historical day archives from existing database data.

    Generates day/YYYY-MM-DD.html and api/day/YYYY-MM-DD.json for one
    specified date using items already stored in the state database.

    Note: This command does NOT fetch new data from sources. It only
    re-renders from existing database content.
    Existing day archives are skipped by default to avoid downgrading
    previously enriched historical pages (e.g., zh translations and
    LLM relevance scores). Use --overwrite-existing to force regeneration.
    """
    from datetime import timedelta

    run_id = str(uuid.uuid4())

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    configure_logging(level=log_level, json_format=json_logs)
    bind_run_context(run_id)

    log = logger.bind(
        run_id=run_id,
        component=COMPONENT_CLI,
        command="backfill",
    )

    # Validate timezone
    try:
        local_tz = zoneinfo.ZoneInfo(timezone)
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        click.echo(f"Error: Invalid timezone '{timezone}'", err=True)
        sys.exit(1)

    # Validate target date
    try:
        datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        click.echo(
            f"Error: Invalid date format '{target_date_str}'. Use YYYY-MM-DD.",
            err=True,
        )
        sys.exit(1)

    log.info(
        "backfill_started",
        target_date=target_date_str,
        state_path=str(state_path),
        output_dir=str(output_dir),
        overwrite_existing=overwrite_existing,
    )

    # Load and validate configuration
    loader = ConfigLoader(run_id=run_id)

    try:
        effective_config = loader.load(
            sources_path=config_path,
            entities_path=entities_path,
            topics_path=topics_path,
        )
    except Exception as e:
        log.warning("config_load_failed", error=str(e))
        click.echo("Configuration validation failed.", err=True)
        sys.exit(1)

    # Get strip params for store
    strip_params = list(effective_config.topics.dedupe.canonical_url_strip_params)

    # Open state store
    with StateStore(
        db_path=state_path,
        strip_params=strip_params,
        run_id=run_id,
    ) as store:
        log.info("store_connected", db_path=str(state_path))

        # Generate archive for one target date
        generated_count = 0
        skipped_existing_count = 0

        # Ensure day directories exist (for HTML routing and JSON data)
        day_dir = output_dir / "day"
        day_dir.mkdir(parents=True, exist_ok=True)
        api_day_dir = output_dir / "api" / "day"
        api_day_dir.mkdir(parents=True, exist_ok=True)

        target_date = target_date_str
        # Preserve already-generated archives unless explicitly forced.
        # This avoids accidental loss of enriched metadata (translations/scores)
        # when backfill re-runs on subsequent days.
        date_json_path = api_day_dir / f"{target_date}.json"
        if date_json_path.exists() and not overwrite_existing:
            skipped_existing_count += 1
            log.info(
                "day_archive_skipped_existing",
                target_date=target_date,
                json_path=str(date_json_path),
            )
        else:
            # Parse the target date
            target_dt_local = datetime.strptime(target_date, "%Y-%m-%d").replace(
                tzinfo=local_tz
            )

            # Build an exact local-day window [00:00, 24:00), then convert to UTC.
            day_start = target_dt_local.astimezone(UTC)
            day_end = (target_dt_local + timedelta(days=1)).astimezone(UTC)

            # Get items published on this date
            items = store.get_items_published_in_range(day_start, day_end)

            log.info(
                "processing_date",
                target_date=target_date,
                items_count=len(items),
            )

            if not items:
                log.info("no_items_for_date", target_date=target_date)
            else:
                # === Run linking ===
                linker = StoryLinker(
                    run_id=run_id,
                    entities_config=effective_config.entities,
                    topics_config=effective_config.topics,
                )
                linker_result = linker.link_items(items)

                # Enrich ranking with cached/new LLM relevance scores when available.
                llm_scores = _run_llm_phase(
                    linker_result,
                    effective_config,
                    run_id,
                    log,
                    output_dir=output_dir,
                )

                # === Run ranking ===
                ranker = StoryRanker(
                    run_id=run_id,
                    topics_config=effective_config.topics,
                    entities_config=effective_config.entities,
                    llm_scores=llm_scores,
                )
                ranker_result = ranker.rank_stories(linker_result.stories)

                # Enrich with zh translations (cached-first, API when available).
                translations = _run_translation_phase(
                    ranker_result,
                    run_id,
                    log,
                    output_dir=output_dir,
                )

                log.info(
                    "backfill_processing",
                    target_date=target_date,
                    stories_count=len(linker_result.stories),
                    top5_count=len(ranker_result.output.top5),
                )

                # === Generate JSON for this date ===
                from src.renderer.json_renderer import JsonRenderer
                from src.renderer.metrics import RendererMetrics

                # For backfill, we don't have fresh fetch data, so sources_status is empty
                # Historical archives focus on content, not source health
                sources_status: list[SourceStatus] = []

                # Build run info for this date
                run_info = RunInfo(
                    run_id=f"{run_id}-{target_date}",
                    started_at=day_start,
                    finished_at=day_end,
                    items_total=len(items),
                    stories_total=len(linker_result.stories),
                    success=True,
                )

                # Get archive dates (scan existing api/day/*.json files)
                archive_dates = set()
                date_str_len = len("YYYY-MM-DD")  # 10 characters
                for json_file in api_day_dir.glob("*.json"):
                    date_str = json_file.stem
                    if len(date_str) == date_str_len:
                        archive_dates.add(date_str)
                archive_dates.add(target_date)
                sorted_archive_dates = sorted(archive_dates, reverse=True)

                # Render JSON for this specific date only (skip daily.json update)
                json_renderer = JsonRenderer(
                    run_id=run_id,
                    output_dir=output_dir,
                    metrics=RendererMetrics.get_instance(),
                    entity_configs=list(effective_config.entities.entities),
                    translations=translations,
                )
                json_renderer.render(
                    ranker_output=ranker_result.output,
                    sources_status=sources_status,
                    run_info=run_info,
                    run_date=target_date,
                    archive_dates=sorted_archive_dates,
                    skip_daily_json=True,  # Don't overwrite daily.json during backfill
                )

                # Create placeholder HTML file (will be replaced by Vue SPA)
                placeholder_path = day_dir / f"{target_date}.html"
                placeholder_content = (
                    f"<!-- Placeholder for {target_date} - replaced by Vue SPA -->\n"
                )
                placeholder_path.write_text(placeholder_content)

                generated_count += 1
                log.info(
                    "day_archive_generated",
                    target_date=target_date,
                    items_count=len(items),
                    stories_count=len(linker_result.stories),
                )

        log.info(
            "backfill_complete",
            days_requested=1,
            days_generated=generated_count,
            days_skipped_existing=skipped_existing_count,
        )

        click.echo(
            "Backfill complete. "
            f"Generated {generated_count} day archives, "
            f"skipped {skipped_existing_count} existing archives."
        )


if __name__ == "__main__":
    cli()
