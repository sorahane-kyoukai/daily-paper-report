"""Unit tests for JSON renderer."""

import json
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.entities import EntityConfig, EntityRegion, EntityType
from src.linker.models import Story, StoryLink
from src.ranker.models import RankerOutput
from src.renderer.json_renderer import JsonRenderer
from src.renderer.metrics import RendererMetrics
from src.renderer.models import RunInfo, SourceStatus, SourceStatusCode


@pytest.fixture
def temp_output_dir() -> Generator[Path]:
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_story() -> Story:
    """Create a sample story for testing."""
    return Story(
        story_id="test-story-1",
        title="Test Story Title",
        primary_link=StoryLink(
            url="https://example.com/article",
            link_type=LinkType.OFFICIAL,
            source_id="test-source",
            tier=0,
            title="Test Story Title",
        ),
        links=[
            StoryLink(
                url="https://example.com/article",
                link_type=LinkType.OFFICIAL,
                source_id="test-source",
                tier=0,
                title="Test Story Title",
            ),
        ],
        entities=["openai"],
        published_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_ranker_output(sample_story: Story) -> RankerOutput:
    """Create sample ranker output."""
    return RankerOutput(
        top5=[sample_story],
        model_releases_by_entity={"openai": [sample_story]},
        papers=[],
        radar=[],
        output_checksum="abc123",
    )


@pytest.fixture
def sample_run_info() -> RunInfo:
    """Create sample run info."""
    return RunInfo(
        run_id="test-run-123",
        started_at=datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 1, 15, 9, 5, 0, tzinfo=UTC),
        success=True,
        items_total=100,
        stories_total=20,
    )


@pytest.fixture
def sample_source_status() -> SourceStatus:
    """Create sample source status."""
    return SourceStatus(
        source_id="test-source",
        name="Test Source",
        tier=0,
        method="rss_atom",
        status=SourceStatusCode.HAS_UPDATE,
        reason_code="ok",
        reason_text="Success",
        items_new=5,
        items_updated=2,
    )


class TestJsonRenderer:
    """Tests for JsonRenderer."""

    def test_render_creates_api_directory(
        self,
        temp_output_dir: Path,
        sample_ranker_output: RankerOutput,
        sample_run_info: RunInfo,
        sample_source_status: SourceStatus,
    ) -> None:
        """Render creates api/ directory."""
        RendererMetrics.reset()
        renderer = JsonRenderer(
            run_id="test",
            output_dir=temp_output_dir,
        )

        renderer.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        assert (temp_output_dir / "api").is_dir()
        assert (temp_output_dir / "api" / "daily.json").is_file()

    def test_render_produces_valid_json(
        self,
        temp_output_dir: Path,
        sample_ranker_output: RankerOutput,
        sample_run_info: RunInfo,
        sample_source_status: SourceStatus,
    ) -> None:
        """Rendered file is valid JSON."""
        RendererMetrics.reset()
        renderer = JsonRenderer(
            run_id="test",
            output_dir=temp_output_dir,
        )

        renderer.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        content = (temp_output_dir / "api" / "daily.json").read_text()
        data = json.loads(content)

        assert data["run_id"] == "test"
        assert data["run_date"] == "2026-01-15"
        assert len(data["top5"]) == 1
        assert data["top5"][0]["title"] == "Test Story Title"

    def test_render_returns_generated_file_info(
        self,
        temp_output_dir: Path,
        sample_ranker_output: RankerOutput,
        sample_run_info: RunInfo,
        sample_source_status: SourceStatus,
    ) -> None:
        """Render returns GeneratedFile with correct info."""
        RendererMetrics.reset()
        renderer = JsonRenderer(
            run_id="test",
            output_dir=temp_output_dir,
        )

        result = renderer.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        assert result.path == "api/daily.json"
        assert result.bytes_written > 0
        assert len(result.sha256) == 64  # SHA-256 hex digest

    def test_render_deterministic_output(
        self,
        temp_output_dir: Path,
        sample_ranker_output: RankerOutput,
        sample_run_info: RunInfo,
        sample_source_status: SourceStatus,
    ) -> None:
        """Same input produces same output (except generated_at)."""
        RendererMetrics.reset()

        # Render twice to different locations
        dir1 = temp_output_dir / "out1"
        dir2 = temp_output_dir / "out2"
        dir1.mkdir()
        dir2.mkdir()

        renderer1 = JsonRenderer(run_id="test", output_dir=dir1)
        renderer2 = JsonRenderer(run_id="test", output_dir=dir2)

        renderer1.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )
        renderer2.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        # Load and compare (ignoring generated_at)
        data1 = json.loads((dir1 / "api" / "daily.json").read_text())
        data2 = json.loads((dir2 / "api" / "daily.json").read_text())

        del data1["generated_at"]
        del data2["generated_at"]

        assert data1 == data2

    def test_render_escapes_special_characters(
        self,
        temp_output_dir: Path,
        sample_run_info: RunInfo,
    ) -> None:
        """Special characters in content are properly escaped."""
        RendererMetrics.reset()

        story_with_special = Story(
            story_id="special-story",
            title='Test <script>alert("xss")</script> Title',
            primary_link=StoryLink(
                url="https://example.com/test",
                link_type=LinkType.OFFICIAL,
                source_id="test",
                tier=0,
                title='Test <script>alert("xss")</script>',
            ),
            links=[
                StoryLink(
                    url="https://example.com/test",
                    link_type=LinkType.OFFICIAL,
                    source_id="test",
                    tier=0,
                )
            ],
        )

        output = RankerOutput(
            top5=[story_with_special],
            model_releases_by_entity={},
            papers=[],
            radar=[],
        )

        renderer = JsonRenderer(run_id="test", output_dir=temp_output_dir)
        renderer.render(
            ranker_output=output,
            sources_status=[],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        content = (temp_output_dir / "api" / "daily.json").read_text()
        # JSON should contain the actual characters (not HTML-escaped)
        # but they should be valid JSON
        data = json.loads(content)
        assert '<script>alert("xss")</script>' in data["top5"][0]["title"]

    def test_render_empty_output(
        self,
        temp_output_dir: Path,
        sample_run_info: RunInfo,
    ) -> None:
        """Can render with empty sections."""
        RendererMetrics.reset()

        output = RankerOutput(
            top5=[],
            model_releases_by_entity={},
            papers=[],
            radar=[],
        )

        renderer = JsonRenderer(run_id="test", output_dir=temp_output_dir)
        result = renderer.render(
            ranker_output=output,
            sources_status=[],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        assert result.bytes_written > 0
        data = json.loads((temp_output_dir / "api" / "daily.json").read_text())
        assert data["top5"] == []
        assert data["radar"] == []

    def test_render_includes_entity_catalog(
        self,
        temp_output_dir: Path,
        sample_ranker_output: RankerOutput,
        sample_run_info: RunInfo,
        sample_source_status: SourceStatus,
    ) -> None:
        """Entity catalog is included when entity_configs are provided."""
        RendererMetrics.reset()

        entity_configs = [
            EntityConfig(
                id="openai",
                name="OpenAI",
                region=EntityRegion.INTL,
                entity_type=EntityType.ORGANIZATION,
                keywords=["OpenAI"],
                prefer_links=[LinkType.OFFICIAL],
            ),
            EntityConfig(
                id="google-research",
                name="Google Research",
                region=EntityRegion.INTL,
                entity_type=EntityType.INSTITUTION,
                keywords=["Google Research"],
                prefer_links=[LinkType.OFFICIAL],
            ),
        ]

        renderer = JsonRenderer(
            run_id="test",
            output_dir=temp_output_dir,
            entity_configs=entity_configs,
        )

        renderer.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        data = json.loads((temp_output_dir / "api" / "daily.json").read_text())
        catalog = data["entity_catalog"]

        assert "openai" in catalog
        assert catalog["openai"]["name"] == "OpenAI"
        assert catalog["openai"]["type"] == "organization"
        assert "google-research" in catalog
        assert catalog["google-research"]["name"] == "Google Research"
        assert catalog["google-research"]["type"] == "institution"

    def test_render_empty_entity_catalog_without_configs(
        self,
        temp_output_dir: Path,
        sample_ranker_output: RankerOutput,
        sample_run_info: RunInfo,
        sample_source_status: SourceStatus,
    ) -> None:
        """Entity catalog is empty when no entity_configs are provided."""
        RendererMetrics.reset()

        renderer = JsonRenderer(
            run_id="test",
            output_dir=temp_output_dir,
        )

        renderer.render(
            ranker_output=sample_ranker_output,
            sources_status=[sample_source_status],
            run_info=sample_run_info,
            run_date="2026-01-15",
        )

        data = json.loads((temp_output_dir / "api" / "daily.json").read_text())
        assert data["entity_catalog"] == {}
