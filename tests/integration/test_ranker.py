"""Integration tests for the ranker module."""

from datetime import UTC, datetime, timedelta

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
from src.ranker import StoryRanker, rank_stories_pure
from src.ranker.state_machine import RankerState


def _make_item(
    url: str,
    source_id: str = "test-source",
    tier: int = 0,
    kind: str = "blog",
    title: str = "Test Item",
    published_at: datetime | None = None,
    raw_json: str = "{}",
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
        raw_json=raw_json,
        first_seen_at=published_at or datetime(2024, 1, 1, tzinfo=UTC),
        last_seen_at=published_at or datetime(2024, 1, 1, tzinfo=UTC),
    )


def _make_story(
    story_id: str,
    title: str = "Test Story",
    source_id: str = "test-source",
    tier: int = 0,
    kind: str = "blog",
    entities: list[str] | None = None,
    published_at: datetime | None = None,
    arxiv_id: str | None = None,
    hf_model_id: str | None = None,
    raw_json: str = "{}",
) -> Story:
    """Create a test Story."""
    url = f"https://example.com/{story_id}"
    link = StoryLink(
        url=url,
        link_type=LinkType.OFFICIAL,
        source_id=source_id,
        tier=tier,
        title=title,
    )

    raw_items = [
        _make_item(
            url=url,
            kind=kind,
            title=title,
            published_at=published_at,
            source_id=source_id,
            raw_json=raw_json,
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


class TestFourOutputSections:
    """Integration tests for all four output sections."""

    def test_all_sections_populated(self) -> None:
        """All four sections are populated from mixed fixture set."""
        now = datetime.now(UTC)

        # Create diverse story set
        stories = [
            # High priority blog posts for top5
            _make_story(
                story_id="blog1",
                title="OpenAI GPT-5 Announcement",
                tier=0,
                kind="blog",
                entities=["openai"],
                published_at=now,
            ),
            _make_story(
                story_id="blog2",
                title="Anthropic Claude Update",
                tier=0,
                kind="blog",
                entities=["anthropic"],
                published_at=now - timedelta(hours=1),
            ),
            # Papers
            _make_story(
                story_id="paper1",
                title="LLM Scaling Laws",
                tier=1,
                kind="paper",
                arxiv_id="2401.00001",
                published_at=now - timedelta(hours=2),
            ),
            _make_story(
                story_id="paper2",
                title="Attention Mechanism Analysis",
                tier=1,
                kind="paper",
                arxiv_id="2401.00002",
                published_at=now - timedelta(hours=3),
            ),
            # Model releases
            _make_story(
                story_id="model1",
                title="Qwen2 Model Release",
                tier=1,
                kind="model",
                hf_model_id="Qwen/Qwen2",
                entities=["qwen"],
                published_at=now - timedelta(hours=4),
            ),
            # Radar items (lower tier or less important)
            _make_story(
                story_id="radar1",
                title="AI Industry News",
                tier=2,
                kind="news",
                published_at=now - timedelta(hours=5),
            ),
            _make_story(
                story_id="radar2",
                title="Forum Discussion on LLMs",
                tier=2,
                kind="forum",
                published_at=now - timedelta(hours=6),
            ),
        ]

        # Configure with entities
        entities = EntitiesConfig(
            entities=[
                EntityConfig(
                    id="openai",
                    name="OpenAI",
                    region="intl",
                    keywords=["OpenAI"],
                    prefer_links=[LinkType.OFFICIAL],
                ),
                EntityConfig(
                    id="anthropic",
                    name="Anthropic",
                    region="intl",
                    keywords=["Anthropic"],
                    prefer_links=[LinkType.OFFICIAL],
                ),
                EntityConfig(
                    id="qwen",
                    name="Qwen",
                    region="cn",
                    keywords=["Qwen"],
                    prefer_links=[LinkType.HUGGINGFACE],
                ),
            ]
        )

        topics = TopicsConfig(
            topics=[
                TopicConfig(
                    name="LLM", keywords=["GPT", "LLM", "Claude"], boost_weight=1.5
                ),
            ],
            quotas=QuotasConfig(top5_max=3, radar_max=5),
        )

        result = rank_stories_pure(
            stories,
            topics_config=topics,
            entities_config=entities,
            now=now,
        )

        # Verify output
        assert result.stories_in == 7
        assert result.stories_out > 0

        # Top 5 should have high priority items
        assert len(result.output.top5) <= 3
        top5_ids = [s.story_id for s in result.output.top5]
        assert "blog1" in top5_ids or "blog2" in top5_ids

        # Papers should have arxiv items
        paper_ids = [s.story_id for s in result.output.papers]
        assert "paper1" in paper_ids or "paper2" in paper_ids

        # Model releases should have the model
        has_model = any(
            any(s.story_id == "model1" for s in stories)
            for stories in result.output.model_releases_by_entity.values()
        )
        # Note: model might be in top5 due to scoring
        assert has_model or "model1" in top5_ids

        # Radar should have lower priority items
        radar_ids = [s.story_id for s in result.output.radar]
        assert len(radar_ids) <= 5

    def test_required_fields_present(self) -> None:
        """Each entry in output has required fields for rendering."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id="s1",
                title="Test Story",
                tier=0,
                published_at=now,
            )
        ]

        result = rank_stories_pure(stories, now=now)

        # Check top5 entries have required fields
        for story in result.output.top5:
            assert story.story_id
            assert story.title
            assert story.primary_link
            assert story.primary_link.url
            assert story.primary_link.link_type
            assert story.links

        # Check checksum is present
        assert result.output.output_checksum
        assert len(result.output.output_checksum) == 64


class TestHighVolumeArxiv:
    """Integration tests for high-volume arXiv scenarios."""

    def test_arxiv_per_category_quota(self) -> None:
        """100 arXiv items result in max 10 kept per category."""
        now = datetime.now(UTC)

        # Create 100 arXiv items (all same category for simplicity)
        stories = [
            _make_story(
                story_id=f"arxiv-{i:03d}",
                title=f"Paper {i}",
                tier=1,
                kind="paper",
                arxiv_id=f"2401.{i:05d}",
                published_at=now - timedelta(hours=i),
                raw_json='{"categories": "cs.AI"}',
            )
            for i in range(100)
        ]

        topics = TopicsConfig(
            quotas=QuotasConfig(
                arxiv_per_category_max=10,
                per_source_max=100,  # Don't limit by source
                top5_max=5,
                radar_max=10,
            )
        )

        result = rank_stories_pure(stories, topics_config=topics, now=now)

        # At most 10 arXiv papers should make it through
        # They might be distributed across sections
        total_in_output = (
            len(result.output.top5)
            + len(result.output.papers)
            + len(result.output.radar)
        )

        assert total_in_output <= 10
        assert result.dropped_total >= 90  # At least 90 dropped

    def test_per_source_quota_with_arxiv(self) -> None:
        """Per-source quota limits arXiv items."""
        now = datetime.now(UTC)

        # 50 arXiv items from same source
        stories = [
            _make_story(
                story_id=f"arxiv-{i:03d}",
                title=f"Paper {i}",
                source_id="arxiv-cs-ai",
                tier=1,
                kind="paper",
                arxiv_id=f"2401.{i:05d}",
                published_at=now - timedelta(hours=i),
            )
            for i in range(50)
        ]

        topics = TopicsConfig(
            quotas=QuotasConfig(
                per_source_max=10,
                arxiv_per_category_max=20,
            )
        )

        result = rank_stories_pure(stories, topics_config=topics, now=now)

        # At most 10 from this source
        assert result.dropped_total >= 40


class TestStableOrdering:
    """Integration tests for stable, deterministic ordering."""

    def test_repeated_runs_identical_output(self) -> None:
        """Multiple runs with same input produce identical output."""
        now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)

        def make_stories() -> list[Story]:
            return [
                _make_story(
                    story_id=f"s{i}",
                    title=f"Story {i}",
                    published_at=now - timedelta(hours=i),
                )
                for i in range(20)
            ]

        topics = TopicsConfig()
        checksums = []

        for run in range(5):
            result = rank_stories_pure(
                make_stories(),
                topics_config=topics,
                now=now,
                run_id=f"run-{run}",
            )
            checksums.append(result.output.output_checksum)

        # All checksums should be identical
        assert all(c == checksums[0] for c in checksums)

    def test_top5_stable_across_runs(self) -> None:
        """Top 5 order is stable across repeated runs."""
        now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)

        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                tier=i % 3,
                published_at=now - timedelta(hours=i),
            )
            for i in range(15)
        ]

        all_top5_orders: list[list[str]] = []

        for _ in range(10):
            result = rank_stories_pure(stories, now=now)
            order = [s.story_id for s in result.output.top5]
            all_top5_orders.append(order)

        # All orders should be identical
        assert all(order == all_top5_orders[0] for order in all_top5_orders)


class TestEndToEndPipeline:
    """End-to-end integration tests."""

    def test_full_pipeline_with_config(self) -> None:
        """Full pipeline with realistic config."""
        now = datetime.now(UTC)

        # Realistic configuration
        entities = EntitiesConfig(
            entities=[
                EntityConfig(
                    id="openai",
                    name="OpenAI",
                    region="intl",
                    keywords=["OpenAI", "GPT-4", "ChatGPT"],
                    prefer_links=[LinkType.OFFICIAL, LinkType.ARXIV],
                ),
                EntityConfig(
                    id="anthropic",
                    name="Anthropic",
                    region="intl",
                    keywords=["Anthropic", "Claude"],
                    prefer_links=[LinkType.OFFICIAL],
                ),
            ]
        )

        topics = TopicsConfig(
            scoring=ScoringConfig(
                tier_0_weight=3.0,
                tier_1_weight=2.0,
                tier_2_weight=1.0,
                topic_match_weight=1.5,
                entity_match_weight=2.0,
                recency_decay_factor=0.1,
            ),
            quotas=QuotasConfig(
                top5_max=5,
                radar_max=10,
                per_source_max=10,
                arxiv_per_category_max=10,
            ),
            topics=[
                TopicConfig(
                    name="LLM",
                    keywords=["LLM", "GPT", "language model"],
                    boost_weight=1.5,
                ),
                TopicConfig(
                    name="Safety", keywords=["safety", "alignment"], boost_weight=1.3
                ),
            ],
        )

        # Mixed story set
        stories = [
            # Official announcements
            _make_story(
                story_id="openai-blog",
                title="OpenAI Announces GPT-5",
                source_id="openai-blog",
                tier=0,
                kind="blog",
                entities=["openai"],
                published_at=now,
            ),
            _make_story(
                story_id="anthropic-blog",
                title="Claude 4 Release",
                source_id="anthropic-blog",
                tier=0,
                kind="blog",
                entities=["anthropic"],
                published_at=now - timedelta(hours=2),
            ),
            # Papers
            _make_story(
                story_id="paper1",
                title="LLM Scaling Analysis",
                source_id="arxiv-cs-ai",
                tier=1,
                kind="paper",
                arxiv_id="2401.00001",
                published_at=now - timedelta(days=1),
            ),
            # News
            _make_story(
                story_id="news1",
                title="AI Industry Round-up",
                source_id="news-site",
                tier=2,
                kind="news",
                published_at=now - timedelta(days=2),
            ),
        ]

        ranker = StoryRanker(
            run_id="e2e-test",
            topics_config=topics,
            entities_config=entities,
            now=now,
        )

        result = ranker.rank_stories(stories)

        # Verify state machine completed
        assert ranker.state == RankerState.ORDERED_OUTPUTS

        # Verify output structure
        assert result.stories_in == 4
        assert result.stories_out > 0
        assert result.output.output_checksum

        # High-tier OpenAI story should be in top5
        top5_ids = [s.story_id for s in result.output.top5]
        assert "openai-blog" in top5_ids

        # Topic hits should include LLM
        assert "LLM" in result.top_topic_hits

        # Percentiles should be calculated
        assert "p50" in result.score_percentiles


class TestBoundaryConditions:
    """Boundary tests for quota limits."""

    def test_exactly_five_stories_fills_top5(self) -> None:
        """Exactly 5 stories should fill Top 5 completely."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                tier=0,
                published_at=now - timedelta(hours=i),
            )
            for i in range(5)
        ]

        topics = TopicsConfig(quotas=QuotasConfig(top5_max=5))
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        assert len(result.output.top5) == 5
        assert len(result.output.radar) == 0

    def test_six_stories_one_to_radar(self) -> None:
        """6 stories: 5 in Top 5, 1 in Radar."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                tier=0,
                kind="news",  # Not paper or model
                published_at=now - timedelta(hours=i),
            )
            for i in range(6)
        ]

        topics = TopicsConfig(quotas=QuotasConfig(top5_max=5, radar_max=10))
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        assert len(result.output.top5) == 5
        # 6th story goes to radar (not paper or model)
        assert len(result.output.radar) == 1

    def test_exactly_ten_radar_fills_quota(self) -> None:
        """15 news stories (no papers/models): 5 in Top 5, 10 in Radar."""
        now = datetime.now(UTC)

        # Use different sources to avoid per_source_max limit
        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                source_id=f"source-{i}",  # Different source for each
                tier=0,
                kind="news",
                published_at=now - timedelta(hours=i),
            )
            for i in range(15)
        ]

        topics = TopicsConfig(
            quotas=QuotasConfig(top5_max=5, radar_max=10, per_source_max=100)
        )
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        assert len(result.output.top5) == 5
        assert len(result.output.radar) == 10
        # 15 - 5 - 10 = 0 (all fit in sections)
        assert result.dropped_total == 0

    def test_radar_overflow_dropped(self) -> None:
        """16 news stories: 5 in Top 5, 10 in Radar, 1 dropped."""
        now = datetime.now(UTC)

        # Use different sources to avoid per_source_max limit
        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                source_id=f"source-{i}",  # Different source for each
                tier=0,
                kind="news",
                published_at=now - timedelta(hours=i),
            )
            for i in range(16)
        ]

        topics = TopicsConfig(
            quotas=QuotasConfig(top5_max=5, radar_max=10, per_source_max=100)
        )
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        assert len(result.output.top5) == 5
        assert len(result.output.radar) == 10
        # 16 - 5 - 10 = 1 dropped
        assert result.dropped_total == 1

    def test_per_source_max_boundary(self) -> None:
        """Exactly per_source_max stories from same source: all kept."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                source_id="same-source",
                tier=0,
                published_at=now - timedelta(hours=i),
            )
            for i in range(10)
        ]

        topics = TopicsConfig(
            quotas=QuotasConfig(per_source_max=10, top5_max=5, radar_max=10)
        )
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        # All 10 should be kept (5 top5 + 5 radar/papers/model_releases)
        total_out = (
            len(result.output.top5)
            + len(result.output.papers)
            + len(result.output.radar)
        )
        assert total_out == 10
        assert result.dropped_total == 0

    def test_per_source_max_plus_one_dropped(self) -> None:
        """11 stories from same source with per_source_max=10: 1 dropped."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id=f"s{i}",
                title=f"Story {i}",
                source_id="same-source",
                tier=0,
                published_at=now - timedelta(hours=i),
            )
            for i in range(11)
        ]

        topics = TopicsConfig(
            quotas=QuotasConfig(per_source_max=10, top5_max=15, radar_max=15)
        )
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        # 1 should be dropped due to per_source_max
        assert result.dropped_total == 1


class TestEdgeCases:
    """Edge case tests for unusual inputs."""

    def test_empty_stories_list(self) -> None:
        """Empty stories list produces empty output."""
        result = rank_stories_pure([])

        assert result.stories_in == 0
        assert result.stories_out == 0
        assert len(result.output.top5) == 0
        assert len(result.output.papers) == 0
        assert len(result.output.radar) == 0
        assert result.output.output_checksum is not None

    def test_no_topics_configured(self) -> None:
        """Stories are ranked even with no topics configured."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id="s1",
                title="Some Story",
                published_at=now,
            )
        ]

        topics = TopicsConfig(topics=[])  # No topics
        result = rank_stories_pure(stories, topics_config=topics, now=now)

        assert result.stories_in == 1
        assert result.stories_out == 1

    def test_no_entities_configured(self) -> None:
        """Stories are ranked even with no entities configured."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id="s1",
                title="Some Story",
                entities=["openai"],  # Story has entity but no config
                published_at=now,
            )
        ]

        result = rank_stories_pure(
            stories, topics_config=TopicsConfig(), entities_config=None, now=now
        )

        assert result.stories_in == 1
        assert result.stories_out == 1

    def test_story_with_no_raw_items(self) -> None:
        """Story with empty raw_items list is handled gracefully."""
        now = datetime.now(UTC)

        # Create story with empty raw_items directly
        link = StoryLink(
            url="https://example.com/s1",
            link_type=LinkType.OFFICIAL,
            source_id="test-source",
            tier=0,
            title="Story without items",
        )
        story = Story(
            story_id="s1",
            title="Story without items",
            primary_link=link,
            links=[link],
            entities=[],
            published_at=now,
            raw_items=[],  # Empty raw_items
        )

        result = rank_stories_pure([story], now=now)

        assert result.stories_in == 1
        assert result.stories_out == 1

    def test_story_with_none_published_at(self) -> None:
        """Story with None published_at gets recency penalty but is processed."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id="dated",
                title="Dated Story",
                published_at=now,
            ),
            _make_story(
                story_id="undated",
                title="Undated Story",
                published_at=None,
            ),
        ]

        result = rank_stories_pure(stories, now=now)

        assert result.stories_in == 2
        assert result.stories_out == 2

        # Dated story should rank higher due to recency
        top_ids = [s.story_id for s in result.output.top5]
        assert top_ids[0] == "dated"

    def test_mixed_arxiv_and_non_arxiv(self) -> None:
        """Mix of arXiv and non-arXiv papers handled correctly."""
        now = datetime.now(UTC)

        stories = [
            _make_story(
                story_id="arxiv1",
                title="ArXiv Paper",
                kind="paper",
                arxiv_id="2401.00001",
                published_at=now,
            ),
            _make_story(
                story_id="non-arxiv",
                title="Non-ArXiv Paper",
                kind="paper",
                arxiv_id=None,
                published_at=now,
            ),
        ]

        result = rank_stories_pure(stories, now=now)

        # Both should be in papers section (after top5 assignment)
        total_papers = len(result.output.papers)
        total_top5 = len(result.output.top5)

        # Both should be in output
        assert total_papers + total_top5 == 2
