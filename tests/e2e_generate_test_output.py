"""Generate test output for E2E validation of sources status feature."""

import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.features.config.schemas.base import LinkType
from src.linker.models import Story, StoryLink
from src.ranker.models import RankerOutput
from src.renderer.models import RunInfo, SourceStatus, SourceStatusCode
from src.renderer.renderer import StaticRenderer


def create_sample_sources_status() -> list[SourceStatus]:
    """Create sample sources status with various statuses for testing."""
    return [
        # International Labs
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
            source_id="google-ai-blog",
            name="Google AI Blog",
            tier=0,
            method="rss_atom",
            status=SourceStatusCode.HAS_UPDATE,
            reason_code="FETCH_PARSE_OK_HAS_UPDATED",
            reason_text="Fetch and parse succeeded; items updated.",
            items_new=0,
            items_updated=2,
            category="intl_labs",
        ),
        # CN Ecosystem
        SourceStatus(
            source_id="baidu-blog",
            name="Baidu AI Blog",
            tier=1,
            method="html_list",
            status=SourceStatusCode.CANNOT_CONFIRM,
            reason_code="DATES_MISSING_NO_ORDERING",
            reason_text="Published dates missing for all items; cannot confirm update status.",
            remediation_hint="Consider using item page date recovery or stable identifiers.",
            items_new=0,
            items_updated=0,
            category="cn_ecosystem",
        ),
        SourceStatus(
            source_id="alibaba-damo",
            name="Alibaba DAMO Academy",
            tier=1,
            method="html_profile",
            status=SourceStatusCode.NO_UPDATE,
            reason_code="FETCH_PARSE_OK_NO_DELTA",
            reason_text="Fetch and parse succeeded; no changes since last run.",
            items_new=0,
            items_updated=0,
            category="cn_ecosystem",
        ),
        # Platforms
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
            source_id="github-trending",
            name="GitHub Trending",
            tier=1,
            method="github_releases",
            status=SourceStatusCode.HAS_UPDATE,
            reason_code="FETCH_PARSE_OK_HAS_NEW",
            reason_text="Fetch and parse succeeded; new items found.",
            newest_item_date=datetime.now(UTC),
            items_new=5,
            items_updated=0,
            category="platforms",
        ),
        SourceStatus(
            source_id="openreview-venue",
            name="OpenReview Venue",
            tier=1,
            method="openreview_venue",
            status=SourceStatusCode.PARSE_FAILED,
            reason_code="PARSE_JSON_ERROR",
            reason_text="Failed to parse JSON content.",
            remediation_hint="Source JSON format may have changed; update schema.",
            items_new=0,
            items_updated=0,
            category="platforms",
        ),
        # Paper Sources
        SourceStatus(
            source_id="arxiv-cs-ai",
            name="arXiv cs.AI",
            tier=0,
            method="arxiv_api",
            status=SourceStatusCode.HAS_UPDATE,
            reason_code="FETCH_PARSE_OK_HAS_NEW",
            reason_text="Fetch and parse succeeded; new items found.",
            newest_item_date=datetime.now(UTC),
            items_new=42,
            items_updated=3,
            category="paper_sources",
        ),
        # Other
        SourceStatus(
            source_id="misc-source",
            name="Miscellaneous Source",
            tier=2,
            method="html_list",
            status=SourceStatusCode.STATUS_ONLY,
            reason_code="STATUS_ONLY_SOURCE",
            reason_text="Source is status-only; no items expected.",
            items_new=0,
            items_updated=0,
            category="other",
        ),
    ]


def create_sample_ranker_output() -> RankerOutput:
    """Create sample ranker output for testing."""
    story = Story(
        story_id="test-story",
        title="Test Story for E2E Validation",
        primary_link=StoryLink(
            url="https://example.com/test",
            link_type=LinkType.OFFICIAL,
            source_id="openai-blog",
            tier=0,
            title="Test Story for E2E Validation",
        ),
        links=[
            StoryLink(
                url="https://example.com/test",
                link_type=LinkType.OFFICIAL,
                source_id="openai-blog",
                tier=0,
                title="Test Story for E2E Validation",
            )
        ],
        entities=["openai"],
        published_at=datetime.now(UTC),
    )
    return RankerOutput(
        top5=[story],
        model_releases_by_entity={"openai": [story]},
        papers=[],
        radar=[story],
        output_checksum="test-checksum",
    )


def generate_test_output(output_dir: Path) -> None:
    """Generate test output for E2E validation."""
    run_id = "e2e-test-run-001"

    ranker_output = create_sample_ranker_output()
    sources_status = create_sample_sources_status()
    run_info = RunInfo(
        run_id=run_id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        success=True,
        items_total=50,
        stories_total=1,
    )

    renderer = StaticRenderer(
        run_id=run_id,
        output_dir=output_dir,
    )

    result = renderer.render(
        ranker_output=ranker_output,
        sources_status=sources_status,
        run_info=run_info,
        recent_runs=[run_info],
    )

    for _f in result.manifest.files:
        pass


if __name__ == "__main__":
    output_dir = Path("/Users/denny_lee/Desktop/Denny/git/temp/public")
    generate_test_output(output_dir)

    # Also output the JSON sources_status for verification
    sources_status = create_sample_sources_status()
    for _s in sources_status:
        pass
