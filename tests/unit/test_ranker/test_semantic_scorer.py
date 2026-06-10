"""Unit tests for embedding-based semantic scorer."""

from __future__ import annotations

import importlib.util
from unittest.mock import MagicMock, patch

import pytest

from src.features.config.schemas.topics import TopicConfig


def _make_topics() -> list[TopicConfig]:
    """Create test topics."""
    return [
        TopicConfig(
            name="LLM",
            keywords=["large language model", "GPT", "transformer"],
            boost_weight=1.5,
        ),
        TopicConfig(
            name="Safety",
            keywords=["alignment", "RLHF", "safety"],
            boost_weight=2.0,
        ),
    ]


# Guard: some tests require numpy (optional dependency)
_HAS_NUMPY = importlib.util.find_spec("numpy") is not None
_skip_no_numpy = pytest.mark.skipif(not _HAS_NUMPY, reason="numpy not installed")


def _make_mock_model(
    n_topics: int = 2,
    *,
    query_matches_topic: int = 0,
) -> MagicMock:
    """Create a mock TextEmbedding model.

    Args:
        n_topics: Number of topics (embedding rows).
        query_matches_topic: Index of the topic the query should match.
    """
    import numpy as np  # type: ignore[import-not-found]

    mock_model = MagicMock()

    # Topic embeddings: orthonormal basis vectors
    topic_vecs = np.eye(384)[:n_topics].astype(np.float32)
    mock_model.passage_embed.return_value = iter(topic_vecs)

    # Query embedding: matches the specified topic exactly
    query_vec = topic_vecs[query_matches_topic].copy()
    mock_model.query_embed.return_value = iter([query_vec])

    # Store for reuse in multi-call tests
    mock_model._topic_vecs = topic_vecs

    return mock_model


class TestIsAvailable:
    """Tests for the is_available() guard function."""

    def test_returns_bool(self) -> None:
        """is_available() returns a boolean."""
        from src.ranker.semantic_scorer import is_available

        assert isinstance(is_available(), bool)


@_skip_no_numpy
class TestSemanticScorerWithMock:
    """Tests for SemanticScorer using mocked fastembed.

    Requires numpy (optional dependency) to build mock embeddings.
    """

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_initialization(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """SemanticScorer initializes with topic embeddings."""
        mock_model = _make_mock_model()
        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        topics = _make_topics()
        scorer = SemanticScorer(topics=topics)

        mock_text_embedding_cls.assert_called_once()
        mock_model.passage_embed.assert_called_once()
        assert len(scorer._topic_names) == 2
        assert scorer._topic_names == ["LLM", "Safety"]
        assert scorer._topic_weights == [1.5, 2.0]

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_above_threshold(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text returns similarity and topic name above threshold."""
        mock_model = _make_mock_model(query_matches_topic=0)
        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics(), similarity_threshold=0.1)

        # Reset query_embed for the actual scoring call
        query_vec = mock_model._topic_vecs[0].copy()
        mock_model.query_embed.return_value = iter([query_vec])

        sim, name = scorer.score_text("large language model research")

        assert sim == pytest.approx(1.0)
        assert name == "LLM"

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_below_threshold(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text returns (0.0, None) when below threshold."""
        import numpy as np

        mock_model = _make_mock_model()
        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics(), similarity_threshold=0.5)

        # Query orthogonal to all topic vectors → similarity = 0
        orthogonal = np.zeros(384, dtype=np.float32)
        orthogonal[300] = 1.0
        mock_model.query_embed.return_value = iter([orthogonal])

        sim, name = scorer.score_text("completely unrelated text")

        assert sim == 0.0
        assert name is None

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_empty_string(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text returns (0.0, None) for empty text."""
        mock_text_embedding_cls.return_value = _make_mock_model()

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics())
        sim, name = scorer.score_text("")

        assert sim == 0.0
        assert name is None

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_whitespace_only(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text returns (0.0, None) for whitespace-only text."""
        mock_text_embedding_cls.return_value = _make_mock_model()

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics())
        sim, name = scorer.score_text("   ")

        assert sim == 0.0
        assert name is None

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_weighted_above_threshold(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text_weighted returns positive score above threshold."""
        mock_model = _make_mock_model(query_matches_topic=0)
        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics(), similarity_threshold=0.1)

        # Reset for scoring call
        query_vec = mock_model._topic_vecs[0].copy()
        mock_model.query_embed.return_value = iter([query_vec])

        score = scorer.score_text_weighted("large language model", weight=1.5)

        assert score > 0.0

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_weighted_empty_returns_zero(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text_weighted returns 0.0 for empty text."""
        mock_text_embedding_cls.return_value = _make_mock_model()

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics())
        score = scorer.score_text_weighted("", weight=1.5)

        assert score == 0.0

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_weighted_includes_topic_boost(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text_weighted multiplies by topic boost_weight and global weight."""
        mock_model = _make_mock_model(query_matches_topic=0)
        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=_make_topics(), similarity_threshold=0.1)

        # Query identical to topic 0 → similarity = 1.0
        query_vec = mock_model._topic_vecs[0].copy()
        mock_model.query_embed.return_value = iter([query_vec])

        score = scorer.score_text_weighted("test", weight=2.0)

        # similarity=1.0 for topic 0 (boost_weight=1.5) → 1.0 * 1.5 * 2.0 = 3.0
        # topic 1 similarity=0.0 (below threshold), not counted
        assert score == pytest.approx(3.0)

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_build_topic_descriptions(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """Topic descriptions combine name and keywords."""
        mock_model = _make_mock_model()
        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        SemanticScorer(topics=_make_topics())

        # Check the descriptions passed to passage_embed
        call_args = mock_model.passage_embed.call_args[0][0]
        assert "LLM: large language model, GPT, transformer" in call_args
        assert "Safety: alignment, RLHF, safety" in call_args

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", True)
    @patch("src.ranker.semantic_scorer.TextEmbedding", create=True)
    def test_score_text_weighted_top_k_limits_topics(
        self,
        mock_text_embedding_cls: MagicMock,
    ) -> None:
        """score_text_weighted uses only top-k matching topics."""
        import numpy as np

        # Create 4 topics, all matching
        topics = [
            TopicConfig(name=f"Topic{i}", keywords=[f"kw{i}"], boost_weight=1.0)
            for i in range(4)
        ]
        mock_model = MagicMock()

        # All topic embeddings identical (high similarity for any query)
        topic_vecs = np.tile(np.array([1.0] + [0.0] * 383, dtype=np.float32), (4, 1))
        mock_model.passage_embed.return_value = iter(topic_vecs)

        # Query matches all topics with similarity=1.0
        query_vec = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        mock_model.query_embed.return_value = iter([query_vec])

        mock_text_embedding_cls.return_value = mock_model

        from src.ranker.semantic_scorer import SemanticScorer

        scorer = SemanticScorer(topics=topics, similarity_threshold=0.1)

        mock_model.query_embed.return_value = iter([query_vec])

        # With max_topics=2, should use top 2 out of 4 matching topics
        score = scorer.score_text_weighted("test", weight=1.0, max_topics=2)

        # 2 topics × 1.0 similarity × 1.0 boost × 1.0 weight = 2.0
        assert score == pytest.approx(2.0)


class TestSemanticScorerUnavailable:
    """Tests for when fastembed is not installed."""

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", False)
    def test_raises_runtime_error_when_unavailable(self) -> None:
        """SemanticScorer raises RuntimeError when fastembed not available."""
        from src.ranker.semantic_scorer import SemanticScorer

        topics = [TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0)]
        with pytest.raises(RuntimeError, match="fastembed is required"):
            SemanticScorer(topics=topics)


class TestScorerSemanticIntegration:
    """Tests for semantic scoring integration in StoryScorer."""

    def test_semantic_disabled_returns_zero(self) -> None:
        """When semantic is disabled, semantic_score is zero."""
        from src.features.config.schemas.base import LinkType
        from src.features.config.schemas.topics import ScoringConfig
        from src.features.store.models import DateConfidence, Item
        from src.linker.models import Story, StoryLink
        from src.ranker.scorer import ScorerConfig, StoryScorer

        topics = [TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0)]
        config = ScorerConfig(
            scoring_config=ScoringConfig(),
            topics=topics,
            enable_semantic=False,
        )
        scorer = StoryScorer(run_id="test", config=config)

        link = StoryLink(
            url="https://example.com/story",
            link_type=LinkType.OFFICIAL,
            source_id="test-source",
            tier=0,
            title="GPT-5",
        )
        item = Item(
            url="https://example.com/item",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="GPT-5",
            published_at=None,
            date_confidence=DateConfidence.LOW,
            content_hash="hash",
            raw_json="{}",
        )
        story = Story(
            story_id="test",
            title="GPT-5",
            primary_link=link,
            links=[link],
            entities=[],
            published_at=None,
            raw_items=[item],
        )

        scored = scorer.score_story(story)
        assert scored.components.semantic_score == 0.0

    @patch("src.ranker.semantic_scorer._FASTEMBED_AVAILABLE", False)
    def test_scorer_graceful_without_fastembed(self) -> None:
        """StoryScorer works gracefully when fastembed not installed."""
        from src.features.config.schemas.base import LinkType
        from src.features.config.schemas.topics import ScoringConfig
        from src.features.store.models import DateConfidence, Item
        from src.linker.models import Story, StoryLink
        from src.ranker.scorer import ScorerConfig, StoryScorer

        topics = [TopicConfig(name="LLM", keywords=["GPT"], boost_weight=1.0)]
        config = ScorerConfig(
            scoring_config=ScoringConfig(),
            topics=topics,
            enable_semantic=True,
        )
        scorer = StoryScorer(run_id="test", config=config)

        link = StoryLink(
            url="https://example.com/story",
            link_type=LinkType.OFFICIAL,
            source_id="test-source",
            tier=0,
            title="GPT-5 Release",
        )
        item = Item(
            url="https://example.com/item",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="GPT-5 Release",
            published_at=None,
            date_confidence=DateConfidence.LOW,
            content_hash="hash",
            raw_json="{}",
        )
        story = Story(
            story_id="test",
            title="GPT-5 Release",
            primary_link=link,
            links=[link],
            entities=[],
            published_at=None,
            raw_items=[item],
        )

        scored = scorer.score_story(story)
        assert scored.components.semantic_score == 0.0
        assert scored.components.total_score > 0.0

    def test_total_score_includes_semantic_component(self) -> None:
        """Total score formula includes semantic_score field."""
        from src.ranker.models import ScoreComponents

        components = ScoreComponents(
            tier_score=3.0,
            kind_score=1.5,
            topic_score=2.0,
            recency_score=0.9,
            entity_score=0.0,
            citation_score=0.3,
            cross_source_score=1.0,
            semantic_score=1.2,
            total_score=9.9,
        )
        assert components.semantic_score == 1.2
        assert "semantic_score" in components.to_dict()
        assert components.to_dict()["semantic_score"] == 1.2
