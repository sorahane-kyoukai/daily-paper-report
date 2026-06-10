"""Integration tests for status rendering end-to-end."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.features.config.schemas.base import LinkType
from src.linker.models import Story, StoryLink
from src.ranker.models import RankerOutput
from src.renderer.models import RunInfo, SourceStatus, SourceStatusCode
from src.renderer.renderer import StaticRenderer


@pytest.fixture
def sample_ranker_output() -> RankerOutput:
    """Create sample ranker output for testing."""
    story = Story(
        story_id="test-story",
        title="Test Story",
        primary_link=StoryLink(
            url="https://example.com/test",
            link_type=LinkType.OFFICIAL,
            source_id="test-source",
            tier=0,
            title="Test Story",
        ),
        links=[
            StoryLink(
                url="https://example.com/test",
                link_type=LinkType.OFFICIAL,
                source_id="test-source",
                tier=0,
                title="Test Story",
            )
        ],
        entities=["test-entity"],
        published_at=datetime.now(UTC),
    )
    return RankerOutput(
        top5=[story],
        model_releases_by_entity={},
        papers=[],
        radar=[],
        output_checksum="test-checksum",
    )


@pytest.fixture
def sample_sources_status() -> list[SourceStatus]:
    """Create sample sources status with various statuses."""
    return [
        SourceStatus(
            source_id="openai-blog",
            name="OpenAI Blog",
            tier=0,
            method="rss_atom",
            status=SourceStatusCode.HAS_UPDATE,
            reason_code="FETCH_PARSE_OK_HAS_NEW",
            reason_text="Fetch and parse succeeded; new items found.",
            items_new=3,
            items_updated=0,
            category="intl_labs",
        ),
        SourceStatus(
            source_id="anthropic-blog",
            name="Anthropic Blog",
            tier=0,
            method="rss_atom",
            status=SourceStatusCode.NO_UPDATE,
            reason_code="FETCH_PARSE_OK_NO_DELTA",
            reason_text="Fetch and parse succeeded; no changes since last run.",
            items_new=0,
            items_updated=0,
            category="intl_labs",
        ),
        SourceStatus(
            source_id="huggingface-blog",
            name="HuggingFace Blog",
            tier=1,
            method="rss_atom",
            status=SourceStatusCode.FETCH_FAILED,
            reason_code="FETCH_TIMEOUT",
            reason_text="HTTP fetch timed out.",
            remediation_hint="Consider increasing timeout or checking network connectivity.",
            items_new=0,
            items_updated=0,
            category="platforms",
        ),
        SourceStatus(
            source_id="baidu-blog",
            name="Baidu AI Blog",
            tier=1,
            method="html_list",
            status=SourceStatusCode.CANNOT_CONFIRM,
            reason_code="DATES_MISSING_NO_ORDERING",
            reason_text="Published dates missing for all items; cannot confirm update status.",
            items_new=0,
            items_updated=0,
            category="cn_ecosystem",
        ),
    ]


class TestStatusRendering:
    """Integration tests for status rendering."""

    def test_json_includes_sources_status(
        self,
        sample_ranker_output: RankerOutput,
        sample_sources_status: list[SourceStatus],
    ) -> None:
        """JSON output includes sources_status array with all fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run_id = "test-run-123"

            run_info = RunInfo(
                run_id=run_id,
                started_at=datetime.now(UTC),
            )

            renderer = StaticRenderer(
                run_id=run_id,
                output_dir=output_dir,
            )

            result = renderer.render(
                ranker_output=sample_ranker_output,
                sources_status=sample_sources_status,
                run_info=run_info,
                recent_runs=[run_info],
            )

            assert result.success

            # Check JSON file
            json_path = output_dir / "api" / "daily.json"
            assert json_path.exists()

            with open(json_path) as f:
                data = json.load(f)

            # Verify sources_status is present
            assert "sources_status" in data
            assert len(data["sources_status"]) == 4

            # Verify structure of first source
            openai = next(
                s for s in data["sources_status"] if s["source_id"] == "openai-blog"
            )
            assert openai["name"] == "OpenAI Blog"
            assert openai["tier"] == 0
            assert openai["method"] == "rss_atom"
            assert openai["status"] == "HAS_UPDATE"
            assert openai["reason_code"] == "FETCH_PARSE_OK_HAS_NEW"
            assert "new items" in openai["reason_text"].lower()
            assert openai["items_new"] == 3
            assert openai["items_updated"] == 0
            assert openai["category"] == "intl_labs"

    def test_json_includes_failed_source_with_remediation_hint(
        self,
        sample_ranker_output: RankerOutput,
        sample_sources_status: list[SourceStatus],
    ) -> None:
        """Failed sources include remediation hints in JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run_id = "test-run-123"

            run_info = RunInfo(
                run_id=run_id,
                started_at=datetime.now(UTC),
            )

            renderer = StaticRenderer(
                run_id=run_id,
                output_dir=output_dir,
            )

            result = renderer.render(
                ranker_output=sample_ranker_output,
                sources_status=sample_sources_status,
                run_info=run_info,
                recent_runs=[run_info],
            )

            assert result.success

            json_path = output_dir / "api" / "daily.json"
            with open(json_path) as f:
                data = json.load(f)

            hf = next(
                s
                for s in data["sources_status"]
                if s["source_id"] == "huggingface-blog"
            )
            assert hf["status"] == "FETCH_FAILED"
            assert hf["remediation_hint"] is not None
            assert "timeout" in hf["remediation_hint"].lower()

    def test_html_sources_page_rendered(
        self,
        sample_ranker_output: RankerOutput,
        sample_sources_status: list[SourceStatus],
    ) -> None:
        """Placeholder day page is rendered for the frontend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run_id = "test-run-123"

            run_info = RunInfo(
                run_id=run_id,
                started_at=datetime.now(UTC),
            )

            renderer = StaticRenderer(
                run_id=run_id,
                output_dir=output_dir,
            )

            result = renderer.render(
                ranker_output=sample_ranker_output,
                sources_status=sample_sources_status,
                run_info=run_info,
                recent_runs=[run_info],
                target_date="2026-01-15",
            )

            assert result.success

            day_path = output_dir / "day" / "2026-01-15.html"
            assert day_path.exists()
            assert "Placeholder" in day_path.read_text()

    def test_html_sources_shows_summary_counts(
        self,
        sample_ranker_output: RankerOutput,
        sample_sources_status: list[SourceStatus],
    ) -> None:
        """JSON output includes sources_status for frontend summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run_id = "test-run-123"

            run_info = RunInfo(
                run_id=run_id,
                started_at=datetime.now(UTC),
            )

            renderer = StaticRenderer(
                run_id=run_id,
                output_dir=output_dir,
            )

            result = renderer.render(
                ranker_output=sample_ranker_output,
                sources_status=sample_sources_status,
                run_info=run_info,
                recent_runs=[run_info],
                target_date="2026-01-15",
            )

            assert result.success

            json_data = json.loads((output_dir / "api" / "daily.json").read_text())
            assert len(json_data["sources_status"]) == 4

    def test_json_reason_codes_are_stable(
        self,
        sample_ranker_output: RankerOutput,
    ) -> None:
        """Reason codes are stable enum values."""
        sources_status = [
            SourceStatus(
                source_id="test-source",
                name="Test Source",
                tier=0,
                method="rss_atom",
                status=SourceStatusCode.NO_UPDATE,
                reason_code="FETCH_PARSE_OK_NO_DELTA",
                reason_text="Test",
                category="other",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run_id = "test-run-1"

            run_info = RunInfo(run_id=run_id, started_at=datetime.now(UTC))
            renderer = StaticRenderer(run_id=run_id, output_dir=output_dir)

            # Render twice with same input
            renderer.render(
                ranker_output=sample_ranker_output,
                sources_status=sources_status,
                run_info=run_info,
                recent_runs=[run_info],
            )

            json_path = output_dir / "api" / "daily.json"
            with open(json_path) as f:
                data1 = json.load(f)

            # Render again
            renderer2 = StaticRenderer(run_id="test-run-2", output_dir=output_dir)
            renderer2.render(
                ranker_output=sample_ranker_output,
                sources_status=sources_status,
                run_info=run_info,
                recent_runs=[run_info],
            )

            with open(json_path) as f:
                data2 = json.load(f)

            # Reason codes should match
            rc1 = data1["sources_status"][0]["reason_code"]
            rc2 = data2["sources_status"][0]["reason_code"]
            assert rc1 == rc2 == "FETCH_PARSE_OK_NO_DELTA"
