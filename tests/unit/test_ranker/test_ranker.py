"""Unit tests for main ranker orchestrator."""

from datetime import UTC, datetime

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.entities import EntitiesConfig, EntityConfig
from src.features.config.schemas.topics import (
    QuotasConfig,
    ScoringConfig,
    TopicConfig,
    TopicsConfig,
)
from src.features.store.models import DateConfidence, Item
from src.linker.models import Story, StoryLink
from src.ranker.ranker import StoryRanker, rank_stories_pure
from src.ranker.state_machine import RankerState


def _make_item(
    url: str = "https://example.com/item",
    source_id: str = "test-source",
    tier: int = 0,
    kind: str = "blog",
    title: str = "Test Item",
    published_at: datetime | None = None,
    first_seen_at: datetime | None = None,
) -> Item:
    """Create a test Item."""
    return Item(
        url=url,
        source_id=source_id,
        tier=tier,
        kind=kind,
        title=title,
        published_at=published_at,
        date_confidence=DateConfidence.HIGH if published_at else DateConfidence.LOW,
        content_hash="test-hash",
        raw_json="{}",
        first_seen_at=first_seen_at or datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    )


def _make_story(
    story_id: str = "test-story-1",
    title: str = "Test Story",
    source_id: str = "test-source",
    tier: int = 0,
    kind: str = "blog",
    entities: list[str] | None = None,
    published_at: datetime | None = None,
    arxiv_id: str | None = None,
    hf_model_id: str | None = None,
) -> Story:
    """Create a test Story."""
    link = StoryLink(
        url=f"https://example.com/{story_id}",
        link_type=LinkType.OFFICIAL,
        source_id=source_id,
        tier=tier,
        title=title,
    )

    raw_items = [
        _make_item(
            url=f"https://example.com/{story_id}",
            kind=kind,
            title=title,
            published_at=published_at,
            source_id=source_id,
        )
    ]

    return Story(
        story_id=story_id,
        title=title,
        primary_link=link,
        links=[link],
        entities=entities or [],
        published_at=published_at,
        arxiv_id=arxiv_id,
        hf_model_id=hf_model_id,
        raw_items=raw_items,
    )


class TestRankerStateTransitions:
    """Tests for ranker state machine integration."""

    def test_full_state_lifecycle(self) -> None:
        """Ranker transitions through all states."""
        ranker = StoryRanker(run_id="test")
        assert ranker.state == RankerState.STORIES_FINAL

        stories = [_make_story(story_id=f"s{i}") for i in range(3)]
        ranker.rank_stories(stories)
        # After state transition, mypy incorrectly narrows state type
        assert ranker.state == RankerState.ORDERED_OUTPUTS  # type: ignore[comparison-overlap]

    def test_empty_input_completes(self) -> None:
        """Empty input still completes state machine."""
        ranker = StoryRanker(run_id="test")

        result = ranker.rank_stories([])

        assert ranker.state == RankerState.ORDERED_OUTPUTS
        assert result.stories_in == 0
        assert result.stories_out == 0


class TestRankerOutput:
    """Tests for ranker output structure."""

    def test_output_has_all_sections(self) -> None:
        """Output contains all four sections."""
        topics = TopicsConfig()
        ranker = StoryRanker(run_id="test", topics_config=topics)

        stories = [
            _make_story(story_id="top1", tier=0),
            _make_story(story_id="paper1", kind="paper", arxiv_id="2401.00001"),
            _make_story(story_id="model1", kind="model", hf_model_id="org/model"),
        ]

        result = ranker.rank_stories(stories)

        assert hasattr(result.output, "top5")
        assert hasattr(result.output, "model_releases_by_entity")
        assert hasattr(result.output, "papers")
        assert hasattr(result.output, "radar")

    def test_top5_limited(self) -> None:
        """Top 5 respects configured max."""
        topics = TopicsConfig(quotas=QuotasConfig(top5_max=3))
        ranker = StoryRanker(run_id="test", topics_config=topics)

        stories = [_make_story(story_id=f"s{i}") for i in range(10)]

        result = ranker.rank_stories(stories)

        assert len(result.output.top5) == 3

    def test_radar_limited(self) -> None:
        """Radar respects configured max."""
        topics = TopicsConfig(quotas=QuotasConfig(top5_max=1, radar_max=2))
        ranker = StoryRanker(run_id="test", topics_config=topics)

        stories = [_make_story(story_id=f"s{i}") for i in range(10)]

        result = ranker.rank_stories(stories)

        assert len(result.output.radar) <= 2

    def test_output_checksum_computed(self) -> None:
        """Output checksum is computed."""
        ranker = StoryRanker(run_id="test")

        stories = [_make_story(story_id="s1")]
        result = ranker.rank_stories(stories)

        assert result.output.output_checksum
        assert len(result.output.output_checksum) == 64  # SHA-256 hex


class TestIdempotency:
    """Tests for idempotent ranking."""

    def test_identical_input_identical_output(self) -> None:
        """Same input produces identical output."""
        now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)

        def make_stories() -> list[Story]:
            return [
                _make_story(story_id="s1", published_at=now),
                _make_story(story_id="s2", published_at=now),
                _make_story(story_id="s3", published_at=now),
            ]

        ranker1 = StoryRanker(run_id="run1", now=now)
        ranker2 = StoryRanker(run_id="run2", now=now)

        result1 = ranker1.rank_stories(make_stories())
        result2 = ranker2.rank_stories(make_stories())

        assert result1.output.output_checksum == result2.output.output_checksum

    def test_different_run_ids_same_result(self) -> None:
        """Different run IDs don't affect output."""
        now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        story = _make_story(story_id="s1", published_at=now)

        result1 = rank_stories_pure([story], now=now, run_id="run1")
        result2 = rank_stories_pure([story], now=now, run_id="run2")

        assert result1.output.output_checksum == result2.output.output_checksum


class TestDropTracking:
    """Tests for dropped story tracking."""

    def test_dropped_entries_tracked(self) -> None:
        """Dropped stories are tracked in result."""
        topics = TopicsConfig(quotas=QuotasConfig(per_source_max=2))
        ranker = StoryRanker(run_id="test", topics_config=topics)

        # 5 stories from same source
        stories = [
            _make_story(story_id=f"s{i}", source_id="same-source") for i in range(5)
        ]

        result = ranker.rank_stories(stories)

        assert result.dropped_total == 3
        assert len(result.dropped_entries) == 3

    def test_dropped_total_matches(self) -> None:
        """dropped_total matches len(dropped_entries)."""
        topics = TopicsConfig(quotas=QuotasConfig(per_source_max=1))
        ranker = StoryRanker(run_id="test", topics_config=topics)

        stories = [_make_story(story_id=f"s{i}", source_id="src") for i in range(10)]

        result = ranker.rank_stories(stories)

        assert result.dropped_total == len(result.dropped_entries)


class TestTopicHits:
    """Tests for topic hit counting."""

    def test_topic_hits_counted(self) -> None:
        """Topic keyword hits are counted."""
        topics = TopicsConfig(
            topics=[
                TopicConfig(name="LLM", keywords=["GPT", "LLM"], boost_weight=1.0),
            ]
        )
        ranker = StoryRanker(run_id="test", topics_config=topics)

        stories = [
            _make_story(story_id="s1", title="GPT-4 release"),
            _make_story(story_id="s2", title="LLM benchmark"),
            _make_story(story_id="s3", title="Unrelated news"),
        ]

        result = ranker.rank_stories(stories)

        assert "LLM" in result.top_topic_hits
        assert result.top_topic_hits["LLM"] >= 2


class TestScorePercentiles:
    """Tests for score percentile calculation."""

    def test_percentiles_calculated(self) -> None:
        """Score percentiles are calculated."""
        ranker = StoryRanker(run_id="test")

        stories = [_make_story(story_id=f"s{i}", tier=i % 3) for i in range(20)]

        result = ranker.rank_stories(stories)

        assert "p50" in result.score_percentiles
        assert "p90" in result.score_percentiles
        assert "p99" in result.score_percentiles


class TestEntityConfiguration:
    """Tests for entity-based scoring."""

    def test_entity_bonus_applied(self) -> None:
        """Stories with configured entities get bonus."""
        entities = EntitiesConfig(
            entities=[
                EntityConfig(
                    id="openai",
                    name="OpenAI",
                    region="intl",
                    keywords=["OpenAI"],
                    prefer_links=[LinkType.OFFICIAL],
                ),
            ]
        )
        topics = TopicsConfig(scoring=ScoringConfig(entity_match_weight=5.0))
        ranker = StoryRanker(
            run_id="test",
            topics_config=topics,
            entities_config=entities,
        )

        # Story with entity should score higher
        story_with_entity = _make_story(story_id="with", entities=["openai"])
        story_without = _make_story(story_id="without", entities=[])

        stories = [story_without, story_with_entity]
        result = ranker.rank_stories(stories)

        # Story with entity should be first (higher score)
        assert result.output.top5[0].story_id == "with"


class TestPureFunctionAPI:
    """Tests for pure function API."""

    def test_rank_stories_pure(self) -> None:
        """Pure function ranks stories correctly."""
        stories = [_make_story(story_id=f"s{i}") for i in range(5)]

        result = rank_stories_pure(stories)

        assert result.stories_in == 5
        assert result.stories_out > 0

    def test_pure_with_config(self) -> None:
        """Pure function accepts config."""
        topics = TopicsConfig(quotas=QuotasConfig(top5_max=2))
        stories = [_make_story(story_id=f"s{i}") for i in range(5)]

        result = rank_stories_pure(stories, topics_config=topics)

        assert len(result.output.top5) == 2
