"""Unit tests for StatusComputer."""

from datetime import UTC, datetime

from src.collectors.base import CollectorResult
from src.collectors.errors import CollectorErrorClass, ErrorRecord
from src.collectors.runner import SourceRunResult
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.status.computer import StatusComputer
from src.features.status.models import ReasonCode, SourceCategory
from src.renderer.models import SourceStatusCode


def make_source_config(
    source_id: str = "test-source",
    name: str = "Test Source",
    method: SourceMethod = SourceMethod.RSS_ATOM,
    tier: SourceTier = SourceTier.TIER_1,
) -> SourceConfig:
    """Create a test source configuration."""
    return SourceConfig(
        id=source_id,
        name=name,
        url="https://example.com/feed",
        tier=tier,
        method=method,
        kind=SourceKind.BLOG,
    )


def make_source_run_result(  # noqa: PLR0913
    source_id: str = "test-source",
    method: str = "rss_atom",
    items_emitted: int = 0,
    items_new: int = 0,
    items_updated: int = 0,
    state: SourceState = SourceState.SOURCE_DONE,
    error: ErrorRecord | None = None,
) -> SourceRunResult:
    """Create a test source run result."""
    return SourceRunResult(
        source_id=source_id,
        method=method,
        result=CollectorResult(
            items=[],
            error=error,
            state=state,
        ),
        items_emitted=items_emitted,
        items_new=items_new,
        items_updated=items_updated,
        upsert_results=[],
    )


class TestStatusComputer:
    """Tests for StatusComputer class."""

    def test_has_update_with_new_items(self) -> None:
        """HAS_UPDATE when new items are found."""
        config = make_source_config()
        result = make_source_run_result(items_emitted=5, items_new=3, items_updated=0)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.status == SourceStatusCode.HAS_UPDATE
        assert status.reason_code == ReasonCode.FETCH_PARSE_OK_HAS_NEW.value
        assert status.items_new == 3
        assert status.items_updated == 0

    def test_has_update_with_updated_items(self) -> None:
        """HAS_UPDATE when items are updated."""
        config = make_source_config()
        result = make_source_run_result(items_emitted=5, items_new=0, items_updated=2)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.status == SourceStatusCode.HAS_UPDATE
        assert status.reason_code == ReasonCode.FETCH_PARSE_OK_HAS_UPDATED.value
        assert status.items_new == 0
        assert status.items_updated == 2

    def test_no_update_when_no_delta(self) -> None:
        """NO_UPDATE when fetch+parse ok but no new/updated items."""
        config = make_source_config()
        result = make_source_run_result(items_emitted=5, items_new=0, items_updated=0)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.status == SourceStatusCode.NO_UPDATE
        assert status.reason_code == ReasonCode.FETCH_PARSE_OK_NO_DELTA.value

    def test_fetch_failed_status(self) -> None:
        """FETCH_FAILED when fetch error occurs."""
        config = make_source_config()
        error = ErrorRecord(
            error_class=CollectorErrorClass.FETCH,
            message="Connection timeout",
            source_id=config.id,
        )
        result = make_source_run_result(
            state=SourceState.SOURCE_FAILED,
            error=error,
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.status == SourceStatusCode.FETCH_FAILED
        assert "FETCH" in status.reason_code

    def test_parse_failed_status(self) -> None:
        """PARSE_FAILED when parse error occurs after successful fetch."""
        config = make_source_config()
        error = ErrorRecord(
            error_class=CollectorErrorClass.PARSE,
            message="Invalid XML",
            source_id=config.id,
        )
        result = make_source_run_result(
            state=SourceState.SOURCE_FAILED,
            error=error,
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.status == SourceStatusCode.PARSE_FAILED
        assert "PARSE" in status.reason_code

    def test_status_only_source(self) -> None:
        """STATUS_ONLY for status-only sources."""
        config = make_source_config(method=SourceMethod.STATUS_ONLY)
        result = make_source_run_result(method="status_only")

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.status == SourceStatusCode.STATUS_ONLY
        assert status.reason_code == ReasonCode.STATUS_ONLY_SOURCE.value

    def test_category_assignment(self) -> None:
        """Category is assigned from source_categories map."""
        config = make_source_config(source_id="openai-blog")
        result = make_source_run_result(source_id="openai-blog", items_new=1)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
            source_categories={"openai-blog": SourceCategory.INTL_LABS},
        )
        status = computer.compute_single(result, config)

        assert status.category == SourceCategory.INTL_LABS.value

    def test_default_category_is_other(self) -> None:
        """Default category is OTHER when not specified."""
        config = make_source_config()
        result = make_source_run_result(items_new=1)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.category == SourceCategory.OTHER.value

    def test_includes_name_and_tier(self) -> None:
        """Status includes source name and tier from config."""
        config = make_source_config(
            name="OpenAI Blog",
            tier=SourceTier.TIER_0,
        )
        result = make_source_run_result(items_new=1)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.name == "OpenAI Blog"
        assert status.tier == 0

    def test_includes_method(self) -> None:
        """Status includes collection method."""
        config = make_source_config(method=SourceMethod.GITHUB_RELEASES)
        result = make_source_run_result(method="github_releases", items_new=1)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert status.method == "github_releases"

    def test_reason_text_populated(self) -> None:
        """Reason text is populated from mapping."""
        config = make_source_config()
        result = make_source_run_result(items_new=1)

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        assert len(status.reason_text) > 0
        assert (
            "new" in status.reason_text.lower()
            or "succeeded" in status.reason_text.lower()
        )


class TestIllegalStatusTransitions:
    """Tests for illegal status transition guards."""

    def test_no_update_requires_fetch_ok(self) -> None:
        """Cannot mark NO_UPDATE if fetch failed."""
        # This is tested implicitly through the classification logic
        # If fetch fails, status will be FETCH_FAILED, not NO_UPDATE
        config = make_source_config()
        error = ErrorRecord(
            error_class=CollectorErrorClass.FETCH,
            message="Timeout",
            source_id=config.id,
        )
        result = make_source_run_result(
            state=SourceState.SOURCE_FAILED,
            error=error,
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        # Must not be NO_UPDATE
        assert status.status != SourceStatusCode.NO_UPDATE
        assert status.status == SourceStatusCode.FETCH_FAILED

    def test_no_update_requires_parse_ok(self) -> None:
        """Cannot mark NO_UPDATE if parse failed."""
        config = make_source_config()
        error = ErrorRecord(
            error_class=CollectorErrorClass.PARSE,
            message="Invalid XML",
            source_id=config.id,
        )
        result = make_source_run_result(
            state=SourceState.SOURCE_FAILED,
            error=error,
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={config.id: config},
        )
        status = computer.compute_single(result, config)

        # Must not be NO_UPDATE
        assert status.status != SourceStatusCode.NO_UPDATE
        assert status.status == SourceStatusCode.PARSE_FAILED


class TestStatusComputerComputeAll:
    """Tests for compute_all method."""

    def test_computes_all_sources(self) -> None:
        """Computes status for all sources in runner result."""
        from src.collectors.runner import RunnerResult

        config1 = make_source_config(source_id="source-1")
        config2 = make_source_config(source_id="source-2")

        now = datetime.now(UTC)
        runner_result = RunnerResult(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            source_results={
                "source-1": make_source_run_result(source_id="source-1", items_new=1),
                "source-2": make_source_run_result(source_id="source-2", items_new=0),
            },
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={"source-1": config1, "source-2": config2},
        )
        statuses = computer.compute_all(runner_result)

        assert len(statuses) == 2
        source_ids = {s.source_id for s in statuses}
        assert "source-1" in source_ids
        assert "source-2" in source_ids

    def test_skips_unknown_sources(self) -> None:
        """Skips sources without config."""
        from src.collectors.runner import RunnerResult

        config1 = make_source_config(source_id="source-1")

        now = datetime.now(UTC)
        runner_result = RunnerResult(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            source_results={
                "source-1": make_source_run_result(source_id="source-1", items_new=1),
                "unknown-source": make_source_run_result(source_id="unknown-source"),
            },
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={"source-1": config1},  # No config for unknown-source
        )
        statuses = computer.compute_all(runner_result)

        assert len(statuses) == 1
        assert statuses[0].source_id == "source-1"

    def test_sorts_by_category_then_id(self) -> None:
        """Statuses are sorted by category then source ID."""
        from src.collectors.runner import RunnerResult

        config_a = make_source_config(source_id="a-source")
        config_b = make_source_config(source_id="b-source")
        config_c = make_source_config(source_id="c-source")

        now = datetime.now(UTC)
        runner_result = RunnerResult(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            source_results={
                "c-source": make_source_run_result(source_id="c-source", items_new=1),
                "a-source": make_source_run_result(source_id="a-source", items_new=1),
                "b-source": make_source_run_result(source_id="b-source", items_new=1),
            },
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs={
                "a-source": config_a,
                "b-source": config_b,
                "c-source": config_c,
            },
            source_categories={
                "a-source": SourceCategory.PLATFORMS,
                "b-source": SourceCategory.INTL_LABS,  # Should come first
                "c-source": SourceCategory.OTHER,
            },
        )
        statuses = computer.compute_all(runner_result)

        # INTL_LABS (b) should come first, then PLATFORMS (a), then OTHER (c)
        assert statuses[0].source_id == "b-source"
        assert statuses[1].source_id == "a-source"
        assert statuses[2].source_id == "c-source"


class TestStatusComputerComputeSummary:
    """Tests for compute_summary method."""

    def test_computes_summary_counts(self) -> None:
        """Computes correct summary counts for each status."""
        from src.collectors.runner import RunnerResult

        configs = {
            f"source-{i}": make_source_config(source_id=f"source-{i}") for i in range(6)
        }

        error_fetch = ErrorRecord(
            error_class=CollectorErrorClass.FETCH,
            message="Timeout",
            source_id="source-3",
        )
        error_parse = ErrorRecord(
            error_class=CollectorErrorClass.PARSE,
            message="Invalid XML",
            source_id="source-4",
        )

        now = datetime.now(UTC)
        runner_result = RunnerResult(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            source_results={
                "source-0": make_source_run_result(
                    source_id="source-0", items_new=3
                ),  # HAS_UPDATE
                "source-1": make_source_run_result(
                    source_id="source-1", items_updated=2
                ),  # HAS_UPDATE
                "source-2": make_source_run_result(
                    source_id="source-2", items_emitted=5
                ),  # NO_UPDATE
                "source-3": make_source_run_result(
                    source_id="source-3",
                    state=SourceState.SOURCE_FAILED,
                    error=error_fetch,
                ),  # FETCH_FAILED
                "source-4": make_source_run_result(
                    source_id="source-4",
                    state=SourceState.SOURCE_FAILED,
                    error=error_parse,
                ),  # PARSE_FAILED
            },
        )

        # Remove source-5 config to avoid mismatch (5 sources in result)
        del configs["source-5"]

        computer = StatusComputer(
            run_id="test-run",
            source_configs=configs,
        )
        statuses = computer.compute_all(runner_result)
        summary = computer.compute_summary(statuses)

        assert summary.total == 5
        assert summary.has_update == 2
        assert summary.no_update == 1
        assert summary.fetch_failed == 1
        assert summary.parse_failed == 1
        assert summary.cannot_confirm == 0
        assert summary.status_only == 0

    def test_summary_failed_total(self) -> None:
        """Summary failed_total is sum of fetch + parse failures."""
        from src.collectors.runner import RunnerResult

        configs = {
            "source-0": make_source_config(source_id="source-0"),
            "source-1": make_source_config(source_id="source-1"),
        }

        error_fetch = ErrorRecord(
            error_class=CollectorErrorClass.FETCH,
            message="Timeout",
            source_id="source-0",
        )
        error_parse = ErrorRecord(
            error_class=CollectorErrorClass.PARSE,
            message="Invalid",
            source_id="source-1",
        )

        now = datetime.now(UTC)
        runner_result = RunnerResult(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            source_results={
                "source-0": make_source_run_result(
                    source_id="source-0",
                    state=SourceState.SOURCE_FAILED,
                    error=error_fetch,
                ),
                "source-1": make_source_run_result(
                    source_id="source-1",
                    state=SourceState.SOURCE_FAILED,
                    error=error_parse,
                ),
            },
        )

        computer = StatusComputer(
            run_id="test-run",
            source_configs=configs,
        )
        statuses = computer.compute_all(runner_result)
        summary = computer.compute_summary(statuses)

        assert summary.failed_total == 2

    def test_summary_empty_list(self) -> None:
        """Summary handles empty status list."""
        computer = StatusComputer(
            run_id="test-run",
            source_configs={},
        )
        summary = computer.compute_summary([])

        assert summary.total == 0
        assert summary.has_update == 0
        assert summary.success_rate == 0.0
