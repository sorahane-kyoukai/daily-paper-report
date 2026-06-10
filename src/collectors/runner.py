"""Collector runner with parallel execution and failure isolation."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from src.collectors.arxiv.api import ArxivApiCollector
from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import CollectorErrorClass, ErrorRecord
from src.collectors.html_list import HtmlListCollector
from src.collectors.metrics import CollectorMetrics
from src.collectors.platform.github import GitHubReleasesCollector
from src.collectors.platform.hf_daily_papers import HuggingFaceDailyPapersCollector
from src.collectors.platform.huggingface import HuggingFaceOrgCollector
from src.collectors.platform.openreview import OpenReviewVenueCollector
from src.collectors.platform.papers_with_code import PapersWithCodeCollector
from src.collectors.rss_atom import RssAtomCollector
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceMethod
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.models import ItemEventType, UpsertResult
from src.features.store.store import StateStore


logger = structlog.get_logger()


@dataclass
class SourceRunResult:
    """Result of running a collector for a single source."""

    source_id: str
    method: str
    result: CollectorResult
    items_emitted: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    duration_ms: float = 0.0
    upsert_results: list[UpsertResult] = field(default_factory=list)


@dataclass
class RunnerResult:
    """Result of a complete runner execution."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    source_results: dict[str, SourceRunResult]
    total_items: int = 0
    total_new: int = 0
    total_updated: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0

    @property
    def success(self) -> bool:
        """Check if any sources succeeded."""
        return self.sources_succeeded > 0

    @property
    def duration_ms(self) -> float:
        """Get total duration in milliseconds."""
        return (self.finished_at - self.started_at).total_seconds() * 1000


class CollectorRunner:
    """Runs collectors for multiple sources with parallel execution.

    Provides:
    - Parallel source processing with configurable concurrency
    - Failure isolation (one source failing doesn't stop others)
    - Automatic collector selection based on source method
    - Item upserts with metrics tracking
    - Structured logging and metrics
    """

    def __init__(  # noqa: PLR0913
        self,
        store: StateStore,
        http_client: HttpFetcher,
        run_id: str,
        max_workers: int = 4,
        strip_params: list[str] | None = None,
        lookback_hours: int = 24,
        max_items_per_source: int | None = None,
    ) -> None:
        """Initialize the collector runner.

        Args:
            store: State store for persistence.
            http_client: HTTP client for fetching.
            run_id: Unique run identifier.
            max_workers: Maximum parallel workers.
            strip_params: URL parameters to strip.
            lookback_hours: Number of hours to look back for items.
            max_items_per_source: Optional per-source max_items override for the run.
                When set, it overrides source_config.max_items.
        """
        self._store = store
        self._http_client = http_client
        self._run_id = run_id
        self._max_workers = max_workers
        self._strip_params = strip_params
        self._lookback_hours = lookback_hours
        self._max_items_per_source = max_items_per_source
        self._metrics = CollectorMetrics.get_instance()
        self._log = logger.bind(
            component="runner",
            run_id=run_id,
        )

        # Initialize collectors
        self._collectors: dict[SourceMethod, BaseCollector] = {
            SourceMethod.RSS_ATOM: RssAtomCollector(strip_params, run_id),
            SourceMethod.ARXIV_API: ArxivApiCollector(strip_params, run_id),
            SourceMethod.HTML_LIST: HtmlListCollector(strip_params, run_id),
            SourceMethod.GITHUB_RELEASES: GitHubReleasesCollector(strip_params, run_id),
            SourceMethod.HF_ORG: HuggingFaceOrgCollector(strip_params, run_id),
            SourceMethod.OPENREVIEW_VENUE: OpenReviewVenueCollector(
                strip_params, run_id
            ),
            SourceMethod.PAPERS_WITH_CODE: PapersWithCodeCollector(
                strip_params, run_id
            ),
            SourceMethod.HF_DAILY_PAPERS: HuggingFaceDailyPapersCollector(
                strip_params, run_id
            ),
        }

    def run(
        self,
        sources: list[SourceConfig],
        now: datetime | None = None,
    ) -> RunnerResult:
        """Run collectors for all sources.

        Args:
            sources: List of source configurations.
            now: Current timestamp (defaults to now).

        Returns:
            RunnerResult with aggregated results.
        """
        now = now or datetime.now(UTC)
        started_at = datetime.now(UTC)

        self._log.info(
            "runner_started",
            source_count=len(sources),
            max_workers=self._max_workers,
        )

        # Filter enabled sources with supported methods
        active_sources = [
            s for s in sources if s.enabled and s.method in self._collectors
        ]

        self._log.info(
            "sources_filtered",
            active_count=len(active_sources),
            skipped_count=len(sources) - len(active_sources),
        )

        # Run collectors in parallel
        source_results: dict[str, SourceRunResult] = {}

        if self._max_workers <= 1:
            # Sequential execution
            for source in active_sources:
                result = self._run_single_source(source, now)
                source_results[source.id] = result
        else:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                future_to_source = {
                    executor.submit(self._run_single_source, source, now): source
                    for source in active_sources
                }

                for future in as_completed(future_to_source):
                    source = future_to_source[future]
                    try:
                        result = future.result()
                        source_results[source.id] = result
                    except Exception as e:  # noqa: BLE001
                        self._log.error(
                            "source_execution_error",
                            source_id=source.id,
                            error=str(e),
                        )
                        source_results[source.id] = SourceRunResult(
                            source_id=source.id,
                            method=source.method.value,
                            result=CollectorResult(
                                items=[],
                                error=ErrorRecord(
                                    error_class=CollectorErrorClass.FETCH,
                                    message=f"Execution error: {e}",
                                    source_id=source.id,
                                ),
                                state=SourceState.SOURCE_FAILED,
                            ),
                        )

        # Aggregate results
        finished_at = datetime.now(UTC)
        total_items = sum(r.items_emitted for r in source_results.values())
        total_new = sum(r.items_new for r in source_results.values())
        total_updated = sum(r.items_updated for r in source_results.values())
        sources_succeeded = sum(1 for r in source_results.values() if r.result.success)
        sources_failed = sum(1 for r in source_results.values() if not r.result.success)

        self._log.info(
            "runner_complete",
            duration_ms=round((finished_at - started_at).total_seconds() * 1000, 2),
            total_items=total_items,
            total_new=total_new,
            total_updated=total_updated,
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
        )

        return RunnerResult(
            run_id=self._run_id,
            started_at=started_at,
            finished_at=finished_at,
            source_results=source_results,
            total_items=total_items,
            total_new=total_new,
            total_updated=total_updated,
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
        )

    def _run_single_source(
        self,
        source: SourceConfig,
        now: datetime,
    ) -> SourceRunResult:
        """Run collector for a single source.

        Args:
            source: Source configuration.
            now: Current timestamp.

        Returns:
            SourceRunResult with items and metrics.
        """
        start_time_ns = time.perf_counter_ns()

        log = self._log.bind(
            source_id=source.id,
            method=source.method.value,
        )

        log.info("source_started")

        collector = self._collectors.get(source.method)
        if not collector:
            log.warning("unsupported_method")
            return SourceRunResult(
                source_id=source.id,
                method=source.method.value,
                result=CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.SCHEMA,
                        message=f"Unsupported method: {source.method.value}",
                        source_id=source.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                ),
            )

        # Run collector
        result = collector.collect(
            source,
            self._http_client,
            now,
            self._lookback_hours,
            self._max_items_per_source,
        )

        # Calculate duration
        duration_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000

        # Record metrics
        self._metrics.record_duration(source.id, duration_ms)

        if result.error:
            self._metrics.record_failure(source.id, result.error.error_class)
            log.warning(
                "source_failed",
                error_class=result.error.error_class.value,
                duration_ms=round(duration_ms, 2),
            )
            return SourceRunResult(
                source_id=source.id,
                method=source.method.value,
                result=result,
                duration_ms=duration_ms,
            )

        # Upsert items to store
        upsert_results: list[UpsertResult] = []
        items_new = 0
        items_updated = 0
        items_unchanged = 0

        for item in result.items:
            upsert_result = self._store.upsert_item(item)
            upsert_results.append(upsert_result)

            if upsert_result.event_type == ItemEventType.NEW:
                items_new += 1
            elif upsert_result.event_type == ItemEventType.UPDATED:
                items_updated += 1
            else:
                items_unchanged += 1

        # Record item metrics
        self._metrics.record_items(source.id, source.kind.value, len(result.items))

        log.info(
            "source_complete",
            items_emitted=len(result.items),
            items_new=items_new,
            items_updated=items_updated,
            items_unchanged=items_unchanged,
            parse_warnings_count=len(result.parse_warnings),
            duration_ms=round(duration_ms, 2),
        )

        return SourceRunResult(
            source_id=source.id,
            method=source.method.value,
            result=result,
            items_emitted=len(result.items),
            items_new=items_new,
            items_updated=items_updated,
            items_unchanged=items_unchanged,
            duration_ms=duration_ms,
            upsert_results=upsert_results,
        )

    def get_supported_methods(self) -> list[SourceMethod]:
        """Get list of supported source methods.

        Returns:
            List of supported SourceMethod values.
        """
        return list(self._collectors.keys())
