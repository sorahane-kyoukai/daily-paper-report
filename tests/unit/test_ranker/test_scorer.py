"""Unit tests for ranker scoring engine."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.topics import ScoringConfig, TopicConfig
from src.features.store.models import DateConfidence, Item
from src.linker.models import Story, StoryLink
from src.ranker.scorer import ScorerConfig, StoryScorer, score_stories_pure


def _make_item(
    url: str = "https://example.com/item",
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
    )


def _make_story(
    story_id: str = "test-story-1",
    title: str = "Test Story",
    tier: int = 0,
    kind: str = "blog",
    entities: list[str] | None = None,
    published_at: datetime | None = None,
    raw_items: list[Item] | None = None,
) -> Story:
    """Create a test Story."""
    link = StoryLink(
        url="https://example.com/story",
        link_type=LinkType.OFFICIAL,
        source_id="test-source",
        tier=tier,
        title=title,
    )

    if raw_items is None:
        raw_items = [
            _make_item(
                kind=kind,
                title=title,
                published_at=published_at,
            )
        ]

    return Story(
        story_id=story_id,
        title=title,
        primary_link=link,
        links=[link],
        entities=entities or [],
        published_at=published_at,
        raw_items=raw_items,
    )


def _make_scorer(
    scoring_config: ScoringConfig | None = None,
    topics: list[TopicConfig] | None = None,
    entity_ids: list[str] | None = None,
    now: datetime | None = None,
) -> StoryScorer:
    """Create a StoryScorer with defaults."""
    config = ScorerConfig(
        scoring_config=scoring_config or ScoringConfig(),
        topics=topics or [],
        entity_ids=entity_ids or [],
        now=now,
    )
    return StoryScorer(run_id="test", config=config)


class TestTierScoring:
    """Tests for tier-based scoring."""

    def test_tier_0_score(self) -> None:
        """Tier 0 gets highest weight."""
        scorer = _make_scorer(
            ScoringConfig(tier_0_weight=3.0, tier_1_weight=2.0, tier_2_weight=1.0)
        )
        story = _make_story(tier=0)
        scored = scorer.score_story(story)
        assert scored.components.tier_score == 3.0

    def test_tier_1_score(self) -> None:
        """Tier 1 gets medium weight."""
        scorer = _make_scorer(
            ScoringConfig(tier_0_weight=3.0, tier_1_weight=2.0, tier_2_weight=1.0)
        )
        story = _make_story(tier=1)
        scored = scorer.score_story(story)
        assert scored.components.tier_score == 2.0

    def test_tier_2_score(self) -> None:
        """Tier 2 gets lowest weight."""
        scorer = _make_scorer(
            ScoringConfig(tier_0_weight=3.0, tier_1_weight=2.0, tier_2_weight=1.0)
        )
        story = _make_story(tier=2)
        scored = scorer.score_story(story)
        assert scored.components.tier_score == 1.0


class TestKindScoring:
    """Tests for kind-based scoring."""

    def test_model_kind_high_score(self) -> None:
        """Model kind gets high weight."""
        scorer = _make_scorer()
        story = _make_story(kind="model")
        scored = scorer.score_story(story)
        # Model kind has 1.8 weight in constants
        assert scored.components.kind_score == 1.8

    def test_blog_kind_score(self) -> None:
        """Blog kind gets expected weight."""
        scorer = _make_scorer()
        story = _make_story(kind="blog")
        scored = scorer.score_story(story)
        assert scored.components.kind_score == 1.5

    def test_unknown_kind_default_score(self) -> None:
        """Unknown kind gets default weight of 1.0."""
        scorer = _make_scorer()
        story = _make_story(kind="unknown_kind")
        scored = scorer.score_story(story)
        assert scored.components.kind_score == 1.0


class TestTopicScoring:
    """Tests for topic keyword matching."""

    def test_topic_match_boosts_score(self) -> None:
        """Matching topic keywords boosts score."""
        topics = [
            TopicConfig(
                name="LLM",
                keywords=["GPT", "language model"],
                boost_weight=1.5,
            )
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.5),
            topics=topics,
        )
        story = _make_story(title="GPT-4 is released")
        scored = scorer.score_story(story)
        # Should get topic boost: 1.5 * 1.5 = 2.25
        assert scored.components.topic_score == pytest.approx(2.25)

    def test_multiple_topics_stack(self) -> None:
        """Multiple matching topics add up."""
        topics = [
            TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0),
            TopicConfig(name="Safety", keywords=["alignment"], boost_weight=1.0),
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.0),
            topics=topics,
        )
        story = _make_story(title="GPT alignment research")
        scored = scorer.score_story(story)
        # Two topics matched: 1.0 * 1.0 + 1.0 * 1.0 = 2.0
        assert scored.components.topic_score == pytest.approx(2.0)

    def test_no_topic_match(self) -> None:
        """No matching topics gives zero boost."""
        topics = [
            TopicConfig(name="LLM", keywords=["GPT", "transformer"], boost_weight=1.5)
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.5),
            topics=topics,
        )
        story = _make_story(title="Unrelated news")
        scored = scorer.score_story(story)
        assert scored.components.topic_score == 0.0

    def test_case_insensitive_matching(self) -> None:
        """Topic matching is case insensitive."""
        topics = [TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0)]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.0),
            topics=topics,
        )
        story = _make_story(title="gpt-4 release")
        scored = scorer.score_story(story)
        assert scored.components.topic_score == 1.0

    def test_abstract_text_matches_topic(self) -> None:
        """Topic keyword in abstract (not title) still boosts score."""
        import json

        topics = [
            TopicConfig(
                name="Reasoning",
                keywords=["chain-of-thought"],
                boost_weight=1.5,
            )
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=2.0),
            topics=topics,
        )
        # Title has no keyword, but abstract does
        raw_json = json.dumps(
            {"summary": "We propose a chain-of-thought prompting method."}
        )
        item = _make_item(title="A Novel Prompting Method", raw_json=raw_json)
        story = _make_story(title="A Novel Prompting Method", raw_items=[item])
        scored = scorer.score_story(story)
        # boost_weight * topic_match_weight = 1.5 * 2.0 = 3.0
        assert scored.components.topic_score == pytest.approx(3.0)

    def test_abstract_snippet_field_matches(self) -> None:
        """abstract_snippet field in raw_json is also searched."""
        import json

        topics = [
            TopicConfig(name="Safety", keywords=["adversarial"], boost_weight=1.0)
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.0),
            topics=topics,
        )
        raw_json = json.dumps(
            {"abstract_snippet": "Adversarial attacks on language models."}
        )
        item = _make_item(title="Robustness Study", raw_json=raw_json)
        story = _make_story(title="Robustness Study", raw_items=[item])
        scored = scorer.score_story(story)
        assert scored.components.topic_score == pytest.approx(1.0)

    def test_no_abstract_still_matches_title(self) -> None:
        """Without abstract, title-only matching still works."""
        topics = [TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0)]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.0),
            topics=topics,
        )
        item = _make_item(title="GPT-5 Release", raw_json="{}")
        story = _make_story(title="GPT-5 Release", raw_items=[item])
        scored = scorer.score_story(story)
        assert scored.components.topic_score == pytest.approx(1.0)

    def test_invalid_raw_json_handled_gracefully(self) -> None:
        """Invalid raw_json doesn't break scoring."""
        topics = [TopicConfig(name="LLM", keywords=["transformer"], boost_weight=1.0)]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.0),
            topics=topics,
        )
        item = _make_item(title="Transformer Paper", raw_json="not valid json")
        story = _make_story(title="Transformer Paper", raw_items=[item])
        scored = scorer.score_story(story)
        # Should still match from title
        assert scored.components.topic_score == pytest.approx(1.0)

    def test_topic_score_cap_limits_total(self) -> None:
        """Topic score is capped at topic_score_cap."""
        topics = [
            TopicConfig(name="LLM", keywords=["GPT"], boost_weight=3.0),
            TopicConfig(name="Safety", keywords=["alignment"], boost_weight=3.0),
            TopicConfig(name="Agents", keywords=["agent"], boost_weight=3.0),
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=2.0, topic_score_cap=10.0),
            topics=topics,
        )
        story = _make_story(title="GPT alignment agent research")
        scored = scorer.score_story(story)
        # Uncapped would be 3 * 3.0 * 2.0 = 18.0, capped at 10.0
        assert scored.components.topic_score == pytest.approx(10.0)

    def test_topic_score_below_cap_not_affected(self) -> None:
        """Topic scores below cap are not affected."""
        topics = [
            TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0),
        ]
        scorer = _make_scorer(
            ScoringConfig(topic_match_weight=1.0, topic_score_cap=15.0),
            topics=topics,
        )
        story = _make_story(title="GPT-4 analysis")
        scored = scorer.score_story(story)
        assert scored.components.topic_score == pytest.approx(1.0)


class TestRecencyScoring:
    """Tests for recency decay scoring."""

    def test_today_high_recency(self) -> None:
        """Story from today has high recency score."""
        now = datetime.now(UTC)
        scorer = _make_scorer(
            ScoringConfig(recency_decay_factor=0.1),
            now=now,
        )
        story = _make_story(published_at=now)
        scored = scorer.score_story(story)
        # e^(-0.1 * 0) = 1.0
        assert scored.components.recency_score == pytest.approx(1.0)

    def test_one_day_old_decay(self) -> None:
        """Story from 1 day ago has decayed score."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        scorer = _make_scorer(
            ScoringConfig(recency_decay_factor=0.1),
            now=now,
        )
        story = _make_story(published_at=yesterday)
        scored = scorer.score_story(story)
        # e^(-0.1 * 1) ≈ 0.905
        expected = math.exp(-0.1 * 1)
        assert scored.components.recency_score == pytest.approx(expected)

    def test_one_week_old_decay(self) -> None:
        """Story from 1 week ago has significantly decayed score."""
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)
        scorer = _make_scorer(
            ScoringConfig(recency_decay_factor=0.1),
            now=now,
        )
        story = _make_story(published_at=week_ago)
        scored = scorer.score_story(story)
        # e^(-0.1 * 7) ≈ 0.497
        expected = math.exp(-0.1 * 7)
        assert scored.components.recency_score == pytest.approx(expected)

    def test_no_date_penalty(self) -> None:
        """Story without date gets penalty."""
        scorer = _make_scorer(ScoringConfig(recency_decay_factor=0.1))
        story = _make_story(published_at=None)
        scored = scorer.score_story(story)
        # Penalty for no date
        assert scored.components.recency_score == pytest.approx(0.1)


class TestEntityScoring:
    """Tests for entity match scoring."""

    def test_entity_match_bonus(self) -> None:
        """Matching entity gives bonus."""
        scorer = _make_scorer(
            ScoringConfig(entity_match_weight=2.0),
            entity_ids=["openai", "anthropic"],
        )
        story = _make_story(entities=["openai"])
        scored = scorer.score_story(story)
        assert scored.components.entity_score == 2.0

    def test_multiple_entity_matches(self) -> None:
        """Multiple entity matches stack."""
        scorer = _make_scorer(
            ScoringConfig(entity_match_weight=2.0),
            entity_ids=["openai", "anthropic"],
        )
        story = _make_story(entities=["openai", "anthropic"])
        scored = scorer.score_story(story)
        # Two matches: 2.0 * 2 = 4.0
        assert scored.components.entity_score == 4.0

    def test_no_entity_match(self) -> None:
        """No matching entity gives zero bonus."""
        scorer = _make_scorer(
            ScoringConfig(entity_match_weight=2.0),
            entity_ids=["openai"],
        )
        story = _make_story(entities=["google"])
        scored = scorer.score_story(story)
        assert scored.components.entity_score == 0.0

    def test_no_entities_in_story(self) -> None:
        """Story without entities gets no bonus."""
        scorer = _make_scorer(
            ScoringConfig(entity_match_weight=2.0),
            entity_ids=["openai"],
        )
        story = _make_story(entities=[])
        scored = scorer.score_story(story)
        assert scored.components.entity_score == 0.0


class TestTotalScore:
    """Tests for total score calculation."""

    def test_total_is_sum_of_components(self) -> None:
        """Total score is sum of all components."""
        now = datetime.now(UTC)
        scorer = _make_scorer(
            ScoringConfig(
                tier_0_weight=3.0,
                topic_match_weight=1.5,
                entity_match_weight=2.0,
                recency_decay_factor=0.0,  # No decay for easy calculation
            ),
            topics=[TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0)],
            entity_ids=["openai"],
            now=now,
        )
        story = _make_story(
            tier=0,
            kind="blog",
            title="GPT-4 release",
            entities=["openai"],
            published_at=now,
        )
        scored = scorer.score_story(story)
        expected = (
            scored.components.tier_score
            + scored.components.kind_score
            + scored.components.topic_score
            + scored.components.recency_score
            + scored.components.entity_score
            + scored.components.citation_score
            + scored.components.cross_source_score
            + scored.components.semantic_score
            + scored.components.llm_relevance_score
        )
        assert scored.components.total_score == pytest.approx(expected)


class TestPureFunction:
    """Tests for pure function API."""

    def test_score_stories_pure(self) -> None:
        """Pure function scores multiple stories."""
        stories = [
            _make_story(story_id="1", title="First story"),
            _make_story(story_id="2", title="Second story"),
        ]
        config = ScorerConfig(scoring_config=ScoringConfig())
        scored = score_stories_pure(stories=stories, config=config)
        assert len(scored) == 2
        assert all(s.components.total_score > 0 for s in scored)


class TestCitationScoring:
    """Tests for citation-based scoring."""

    def test_no_citation_data_zero_score(self) -> None:
        """Story without citation data gets zero citation score."""
        scorer = _make_scorer(ScoringConfig(citation_weight=0.5))
        story = _make_story()
        scored = scorer.score_story(story)
        assert scored.components.citation_score == 0.0

    def test_citation_count_contributes_to_score(self) -> None:
        """Story with citation count gets positive citation score."""
        import json

        raw_json = json.dumps({"citation_count": 100})
        item = _make_item(raw_json=raw_json)
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(
            ScoringConfig(citation_weight=0.5, citation_normalization_cap=1000)
        )
        scored = scorer.score_story(story)

        # log(1 + 100) / log(1 + 1000) * 0.5 ≈ 0.333
        expected = math.log(1 + 100) / math.log(1 + 1000) * 0.5
        assert scored.components.citation_score == pytest.approx(expected, rel=0.01)

    def test_high_citation_count_normalized(self) -> None:
        """High citation count is normalized and capped."""
        import json

        raw_json = json.dumps({"citation_count": 10000})
        item = _make_item(raw_json=raw_json)
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(
            ScoringConfig(citation_weight=0.5, citation_normalization_cap=1000)
        )
        scored = scorer.score_story(story)

        # Should be capped at weight since citations exceed cap
        assert scored.components.citation_score <= 0.5

    def test_max_citation_from_multiple_items(self) -> None:
        """Takes max citation count when multiple items present."""
        import json

        item1 = _make_item(raw_json=json.dumps({"citation_count": 50}))
        item2 = _make_item(
            url="https://example.com/item2",
            raw_json=json.dumps({"citation_count": 200}),
        )
        story = _make_story(raw_items=[item1, item2])

        scorer = _make_scorer(
            ScoringConfig(citation_weight=0.5, citation_normalization_cap=1000)
        )
        scored = scorer.score_story(story)

        # Should use 200, not 50
        expected = math.log(1 + 200) / math.log(1 + 1000) * 0.5
        assert scored.components.citation_score == pytest.approx(expected, rel=0.01)

    def test_invalid_citation_data_graceful(self) -> None:
        """Invalid citation data is handled gracefully."""
        import json

        raw_json = json.dumps({"citation_count": "invalid"})
        item = _make_item(raw_json=raw_json)
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(ScoringConfig(citation_weight=0.5))
        scored = scorer.score_story(story)

        assert scored.components.citation_score == 0.0


class TestCrossSourceScoring:
    """Tests for cross-source quality signal scoring."""

    def test_no_quality_signals_zero_score(self) -> None:
        """Story without quality signals gets zero score."""
        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        story = _make_story()
        scored = scorer.score_story(story)
        assert scored.components.cross_source_score == 0.0

    def test_papers_with_code_source_bonus(self) -> None:
        """Item from papers_with_code source gets bonus."""
        item = _make_item(source_id="papers_with_code")
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        scored = scorer.score_story(story)

        assert scored.components.cross_source_score == 1.0

    def test_hf_daily_papers_source_bonus(self) -> None:
        """Item from hf_daily_papers source gets bonus."""
        item = _make_item(source_id="hf_daily_papers")
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        scored = scorer.score_story(story)

        assert scored.components.cross_source_score == 1.0

    def test_multiple_quality_sources_stack(self) -> None:
        """Multiple quality sources stack up to cap."""
        item1 = _make_item(source_id="papers_with_code")
        item2 = _make_item(url="https://example.com/item2", source_id="hf_daily_papers")
        story = _make_story(raw_items=[item1, item2])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        scored = scorer.score_story(story)

        # Two sources: 1.0 + 1.0 = 2.0
        assert scored.components.cross_source_score == 2.0

    def test_cross_source_score_capped(self) -> None:
        """Cross-source score is capped at max."""

        # Create story with both source IDs and raw_json flags
        item1 = _make_item(source_id="papers_with_code")
        item2 = _make_item(url="https://example.com/item2", source_id="hf_daily_papers")
        story = _make_story(raw_items=[item1, item2])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=2.0))
        scored = scorer.score_story(story)

        # 2 sources * 2.0 weight = 4.0, but capped at 3.0
        assert scored.components.cross_source_score == 3.0

    def test_raw_json_quality_signal_flags(self) -> None:
        """Quality signal flags in raw_json are detected."""
        import json

        raw_json = json.dumps({"from_papers_with_code": True})
        item = _make_item(source_id="other-source", raw_json=raw_json)
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        scored = scorer.score_story(story)

        assert scored.components.cross_source_score == 1.0

    def test_arxiv_api_source_bonus(self) -> None:
        """Item from arXiv API keyword source gets quality signal bonus."""
        item = _make_item(source_id="arxiv-api-llm")
        story = _make_story(raw_items=[item])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        scored = scorer.score_story(story)

        assert scored.components.cross_source_score == 1.0

    def test_rss_plus_api_sources_stack(self) -> None:
        """Paper found in both RSS and API gets stacked bonus."""
        item_rss = _make_item(source_id="arxiv-cs-ai")
        item_api = _make_item(
            url="https://example.com/item2",
            source_id="arxiv-api-llm",
        )
        story = _make_story(raw_items=[item_rss, item_api])

        scorer = _make_scorer(ScoringConfig(cross_source_weight=1.0))
        scored = scorer.score_story(story)

        # Only API source is a quality signal, RSS is not
        assert scored.components.cross_source_score == 1.0


class TestLlmRelevanceScoring:
    """Tests for LLM relevance-based scoring."""

    def test_no_llm_scores_zero_contribution(self) -> None:
        """Story without LLM score gets zero contribution."""
        scorer = _make_scorer(ScoringConfig(llm_relevance_weight=2.0))
        story = _make_story()
        scored = scorer.score_story(story)
        assert scored.components.llm_relevance_score == 0.0

    def test_llm_score_applied_with_weight(self) -> None:
        """LLM score is multiplied by configured weight."""
        config = ScorerConfig(
            scoring_config=ScoringConfig(llm_relevance_weight=2.0),
            llm_scores={"test-story-1": 0.8},
        )
        scorer = StoryScorer(run_id="test", config=config)
        story = _make_story(story_id="test-story-1")
        scored = scorer.score_story(story)
        # 0.8 * 2.0 = 1.6
        assert scored.components.llm_relevance_score == pytest.approx(1.6)

    def test_llm_score_included_in_total(self) -> None:
        """LLM relevance score contributes to total."""
        now = datetime.now(UTC)
        config = ScorerConfig(
            scoring_config=ScoringConfig(
                recency_decay_factor=0.0,
                llm_relevance_weight=2.0,
            ),
            llm_scores={"test-story-1": 0.5},
            now=now,
        )
        scorer = StoryScorer(run_id="test", config=config)
        story = _make_story(story_id="test-story-1", published_at=now)
        scored = scorer.score_story(story)
        # LLM contribution: 0.5 * 2.0 = 1.0
        assert scored.components.llm_relevance_score == pytest.approx(1.0)
        # Total should include all components
        expected = (
            scored.components.tier_score
            + scored.components.kind_score
            + scored.components.topic_score
            + scored.components.recency_score
            + scored.components.entity_score
            + scored.components.citation_score
            + scored.components.cross_source_score
            + scored.components.semantic_score
            + scored.components.llm_relevance_score
        )
        assert scored.components.total_score == pytest.approx(expected)

    def test_missing_story_id_gets_zero(self) -> None:
        """Story not in llm_scores dict gets zero score."""
        config = ScorerConfig(
            scoring_config=ScoringConfig(llm_relevance_weight=2.0),
            llm_scores={"other-story": 0.9},
        )
        scorer = StoryScorer(run_id="test", config=config)
        story = _make_story(story_id="test-story-1")
        scored = scorer.score_story(story)
        assert scored.components.llm_relevance_score == 0.0


class TestTotalScoreWithNewComponents:
    """Tests for total score including new components."""

    def test_total_includes_citation_and_cross_source(self) -> None:
        """Total score includes citation and cross-source scores."""
        import json

        now = datetime.now(UTC)
        raw_json = json.dumps({"citation_count": 100})
        item = _make_item(
            source_id="papers_with_code",
            raw_json=raw_json,
            published_at=now,
        )
        story = _make_story(
            tier=0,
            kind="paper",
            title="Research Paper",
            raw_items=[item],
            published_at=now,
        )

        scorer = _make_scorer(
            ScoringConfig(
                tier_0_weight=3.0,
                recency_decay_factor=0.0,
                citation_weight=0.5,
                citation_normalization_cap=1000,
                cross_source_weight=1.0,
            ),
            now=now,
        )
        scored = scorer.score_story(story)

        # Total should include all components
        expected = (
            scored.components.tier_score
            + scored.components.kind_score
            + scored.components.topic_score
            + scored.components.recency_score
            + scored.components.entity_score
            + scored.components.citation_score
            + scored.components.cross_source_score
            + scored.components.semantic_score
            + scored.components.llm_relevance_score
        )
        assert scored.components.total_score == pytest.approx(expected)
