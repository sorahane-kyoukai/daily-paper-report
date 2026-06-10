"""Unit tests for renderer models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.renderer.models import (
    DailyDigest,
    GeneratedFile,
    RenderContext,
    RenderManifest,
    RenderResult,
    RunInfo,
    SourceStatus,
    SourceStatusCode,
)


class TestSourceStatusCode:
    """Tests for SourceStatusCode enum."""

    def test_all_values_exist(self) -> None:
        """All expected status codes exist."""
        assert SourceStatusCode.NO_UPDATE.value == "NO_UPDATE"
        assert SourceStatusCode.HAS_UPDATE.value == "HAS_UPDATE"
        assert SourceStatusCode.FETCH_FAILED.value == "FETCH_FAILED"
        assert SourceStatusCode.PARSE_FAILED.value == "PARSE_FAILED"
        assert SourceStatusCode.STATUS_ONLY.value == "STATUS_ONLY"
        assert SourceStatusCode.CANNOT_CONFIRM.value == "CANNOT_CONFIRM"


class TestSourceStatus:
    """Tests for SourceStatus model."""

    def test_minimal_creation(self) -> None:
        """Can create with minimal fields."""
        status = SourceStatus(source_id="test-source")
        assert status.source_id == "test-source"
        assert status.status == SourceStatusCode.NO_UPDATE

    def test_full_creation(self) -> None:
        """Can create with all fields."""
        now = datetime.now(UTC)
        status = SourceStatus(
            source_id="arxiv-rss",
            name="arXiv RSS",
            tier=0,
            method="rss_atom",
            status=SourceStatusCode.HAS_UPDATE,
            reason_code="fetch_ok_parse_ok_delta_gt_0",
            reason_text="Fetched successfully with new items",
            remediation_hint=None,
            newest_item_date=now,
            last_fetch_status_code=200,
            items_new=5,
            items_updated=2,
        )
        assert status.name == "arXiv RSS"
        assert status.items_new == 5

    def test_source_id_required(self) -> None:
        """source_id is required."""
        with pytest.raises(ValidationError):
            SourceStatus()  # type: ignore[call-arg]


class TestRunInfo:
    """Tests for RunInfo model."""

    def test_minimal_creation(self) -> None:
        """Can create with minimal fields."""
        now = datetime.now(UTC)
        info = RunInfo(run_id="test-run", started_at=now)
        assert info.run_id == "test-run"
        assert info.finished_at is None
        assert info.success is None

    def test_full_creation(self) -> None:
        """Can create with all fields."""
        now = datetime.now(UTC)
        info = RunInfo(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            success=True,
            items_total=100,
            stories_total=20,
        )
        assert info.success is True
        assert info.items_total == 100


class TestDailyDigest:
    """Tests for DailyDigest model."""

    def test_minimal_creation(self) -> None:
        """Can create with minimal fields."""
        digest = DailyDigest(
            run_id="test-run",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        assert digest.run_date == "2026-01-15"
        assert digest.top5 == []

    def test_run_date_format_validation(self) -> None:
        """run_date must be YYYY-MM-DD format."""
        with pytest.raises(ValidationError):
            DailyDigest(
                run_id="test",
                run_date="invalid-date",
                generated_at="2026-01-15T00:00:00Z",
            )

    def test_with_sections(self) -> None:
        """Can include sections data."""
        digest = DailyDigest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
            top5=[{"title": "Story 1"}],
            radar=[{"title": "Radar 1"}],
        )
        assert len(digest.top5) == 1
        assert len(digest.radar) == 1

    def test_entity_catalog_default_empty(self) -> None:
        """entity_catalog defaults to empty dict."""
        digest = DailyDigest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        assert digest.entity_catalog == {}

    def test_entity_catalog_with_entries(self) -> None:
        """entity_catalog stores entity ID to detail mappings."""
        catalog = {
            "openai": {"name": "OpenAI", "type": "organization"},
            "mit": {"name": "MIT", "type": "institution"},
        }
        digest = DailyDigest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
            entity_catalog=catalog,
        )
        assert digest.entity_catalog["openai"]["name"] == "OpenAI"
        assert digest.entity_catalog["mit"]["type"] == "institution"
        assert len(digest.entity_catalog) == 2


class TestGeneratedFile:
    """Tests for GeneratedFile dataclass."""

    def test_creation(self) -> None:
        """Can create GeneratedFile."""
        gf = GeneratedFile(
            path="api/daily.json",
            absolute_path="/var/out/api/daily.json",  # noqa: S108
            bytes_written=1234,
            sha256="abc123",
        )
        assert gf.path == "api/daily.json"
        assert gf.bytes_written == 1234


class TestRenderManifest:
    """Tests for RenderManifest dataclass."""

    def test_creation(self) -> None:
        """Can create RenderManifest."""
        manifest = RenderManifest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        assert manifest.total_bytes == 0
        assert manifest.files == []

    def test_add_file(self) -> None:
        """add_file updates total_bytes."""
        manifest = RenderManifest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        gf = GeneratedFile(
            path="test.html",
            absolute_path="/var/out/test.html",  # noqa: S108
            bytes_written=500,
            sha256="abc",
        )
        manifest.add_file(gf)
        assert manifest.total_bytes == 500
        assert len(manifest.files) == 1

        gf2 = GeneratedFile(
            path="test2.html",
            absolute_path="/var/out/test2.html",  # noqa: S108
            bytes_written=300,
            sha256="def",
        )
        manifest.add_file(gf2)
        assert manifest.total_bytes == 800
        assert len(manifest.files) == 2


class TestRenderContext:
    """Tests for RenderContext dataclass."""

    def test_creation(self) -> None:
        """Can create RenderContext."""
        ctx = RenderContext(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        assert ctx.timezone == "UTC"
        assert ctx.top5 == []
        assert ctx.archive_dates == []


class TestRenderResult:
    """Tests for RenderResult dataclass."""

    def test_success_result(self) -> None:
        """Can create success result."""
        manifest = RenderManifest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        result = RenderResult(success=True, manifest=manifest)
        assert result.success
        assert result.error_summary is None

    def test_failure_result(self) -> None:
        """Can create failure result."""
        manifest = RenderManifest(
            run_id="test",
            run_date="2026-01-15",
            generated_at="2026-01-15T00:00:00Z",
        )
        result = RenderResult(
            success=False,
            manifest=manifest,
            error_summary="Template error",
        )
        assert not result.success
        assert result.error_summary == "Template error"
