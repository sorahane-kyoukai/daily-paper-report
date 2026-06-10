"""Scoring engine for Story ranking."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.features.config.schemas.topics import ScoringConfig, TopicConfig
from src.linker.models import Story
from src.ranker.constants import (
    CROSS_SOURCE_SCORE_CAP,
    DEFAULT_KIND_WEIGHTS,
    MAX_RECENCY_DAYS,
    QUALITY_SIGNAL_SOURCES,
)
from src.ranker.models import ScoreComponents, ScoredStory
from src.ranker.semantic_scorer import (
    SemanticScorer,
    is_available as _semantic_available,
)
from src.ranker.topic_matcher import TopicMatcher


if TYPE_CHECKING:
    from src.features.store.models import Item


logger = structlog.get_logger()


@dataclass
class ScorerConfig:
    """Configuration bundle for StoryScorer.

    Attributes:
        scoring_config: Scoring weights configuration.
        topics: Topic configurations for keyword matching.
        entity_ids: List of configured entity IDs for bonus.
        now: Current time for recency calculation.
        enable_semantic: Whether to use embedding-based semantic scoring.
    """

    scoring_config: ScoringConfig
    topics: list[TopicConfig] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    now: datetime | None = None
    enable_semantic: bool = True
    llm_scores: dict[str, float] = field(default_factory=dict)


class StoryScorer:
    """Computes numeric scores for Stories based on configurable weights.

    Scoring formula:
        score = tier_score + kind_score + topic_score + recency_score
              + entity_score + citation_score + cross_source_score
              + semantic_score

    Where:
        - tier_score: Based on primary link tier (0/1/2) and tier weights
        - kind_score: Based on source kind (blog/paper/model/etc)
        - topic_score: Sum of matched topic boosts
        - recency_score: Exponential decay based on age
        - entity_score: Bonus for matching configured entities
        - citation_score: Bonus based on Semantic Scholar citation count
        - cross_source_score: Bonus for appearing in quality signal sources
        - semantic_score: Embedding-based semantic similarity to topics
    """

    def __init__(self, run_id: str, config: ScorerConfig) -> None:
        """Initialize the scorer.

        Args:
            run_id: Run identifier for logging.
            config: Scorer configuration bundle.
        """
        self._run_id = run_id
        self._scoring = config.scoring_config
        self._topics = config.topics
        self._entity_ids = set(config.entity_ids)
        self._now = config.now or datetime.now(UTC)
        self._llm_scores = config.llm_scores
        self._log = logger.bind(
            component="ranker",
            subcomponent="scorer",
            run_id=run_id,
        )

        # Use TopicMatcher for pre-compiled patterns
        self._topic_matcher = TopicMatcher(self._topics)

        # Initialize semantic scorer if available and enabled
        self._semantic_scorer: SemanticScorer | None = None
        if config.enable_semantic and self._topics and _semantic_available():
            try:
                self._semantic_scorer = SemanticScorer(
                    topics=self._topics,
                    similarity_threshold=self._scoring.semantic_similarity_threshold,
                )
            except Exception:  # noqa: BLE001
                self._log.warning("semantic_scorer_init_failed", exc_info=True)

    def score_story(self, story: Story) -> ScoredStory:
        """Compute score for a single story.

        Args:
            story: Story to score.

        Returns:
            ScoredStory with computed components.
        """
        tier_score = self._compute_tier_score(story)
        kind_score = self._compute_kind_score(story)
        topic_score = self._compute_topic_score(story)
        recency_score = self._compute_recency_score(story)
        entity_score = self._compute_entity_score(story)
        citation_score = self._compute_citation_score(story)
        cross_source_score = self._compute_cross_source_score(story)
        semantic_score = self._compute_semantic_score(story)
        llm_relevance_score = self._compute_llm_relevance_score(story)

        total_score = (
            tier_score
            + kind_score
            + topic_score
            + recency_score
            + entity_score
            + citation_score
            + cross_source_score
            + semantic_score
            + llm_relevance_score
        )

        components = ScoreComponents(
            tier_score=tier_score,
            kind_score=kind_score,
            topic_score=topic_score,
            recency_score=recency_score,
            entity_score=entity_score,
            citation_score=citation_score,
            cross_source_score=cross_source_score,
            semantic_score=semantic_score,
            llm_relevance_score=llm_relevance_score,
            total_score=total_score,
        )

        return ScoredStory(story=story, components=components)

    def score_stories(self, stories: list[Story]) -> list[ScoredStory]:
        """Score multiple stories.

        Args:
            stories: Stories to score.

        Returns:
            List of ScoredStory objects.
        """
        scored = [self.score_story(story) for story in stories]

        self._log.info(
            "scoring_complete",
            stories_scored=len(scored),
            min_score=min((s.components.total_score for s in scored), default=0.0),
            max_score=max((s.components.total_score for s in scored), default=0.0),
        )

        return scored

    def _compute_tier_score(self, story: Story) -> float:
        """Compute tier-based score.

        Args:
            story: Story to score.

        Returns:
            Tier score component.
        """
        tier = story.primary_link.tier
        if tier == 0:
            return self._scoring.tier_0_weight
        if tier == 1:
            return self._scoring.tier_1_weight
        return self._scoring.tier_2_weight

    def _compute_kind_score(self, story: Story) -> float:
        """Compute kind-based score.

        Args:
            story: Story to score.

        Returns:
            Kind score component.
        """
        # Get kind from the first raw item if available
        if story.raw_items:
            kind = story.raw_items[0].kind.lower()
        else:
            # Fallback: infer from link type
            kind = story.primary_link.link_type.value.lower()

        return DEFAULT_KIND_WEIGHTS.get(kind, 1.0)

    def _compute_topic_score(self, story: Story) -> float:
        """Compute topic keyword match score.

        Builds match text from story title, raw item titles, and
        abstracts/summaries extracted from raw_json metadata.

        Args:
            story: Story to score.

        Returns:
            Topic score component (sum of matched topic boosts).
        """
        text_to_match = story.title.lower()

        for item in story.raw_items:
            text_to_match += " " + item.title.lower()
            # Include abstract/summary for richer keyword matching
            abstract = self._extract_abstract(item)
            if abstract:
                text_to_match += " " + abstract.lower()

        raw_score = self._topic_matcher.compute_boost_score(
            text_to_match, self._scoring.topic_match_weight
        )
        return min(raw_score, self._scoring.topic_score_cap)

    @staticmethod
    def _extract_abstract(item: Item) -> str | None:
        """Extract abstract or summary text from an item's raw_json.

        Args:
            item: Item with raw_json metadata.

        Returns:
            Abstract text if available, None otherwise.
        """
        try:
            raw = json.loads(item.raw_json)
        except (json.JSONDecodeError, TypeError):
            return None

        for field_name in ("abstract_snippet", "summary", "readme_summary"):
            value = raw.get(field_name)
            if isinstance(value, str) and value:
                return value
        return None

    def _compute_recency_score(self, story: Story) -> float:
        """Compute recency decay score.

        Uses exponential decay: e^(-decay_factor * days_old)

        Args:
            story: Story to score.

        Returns:
            Recency score component (0.0 to 1.0).
        """
        if story.published_at is None:
            # Penalize stories without dates
            return 0.1

        age = self._now - story.published_at
        days_old = age.total_seconds() / (24 * 60 * 60)

        # Cap age to prevent extreme penalties
        days_old = min(days_old, MAX_RECENCY_DAYS)

        # Exponential decay
        return math.exp(-self._scoring.recency_decay_factor * days_old)

    def _compute_entity_score(self, story: Story) -> float:
        """Compute entity match bonus.

        Args:
            story: Story to score.

        Returns:
            Entity score component.
        """
        if not story.entities:
            return 0.0

        # Count how many configured entities match
        matched = sum(1 for eid in story.entities if eid in self._entity_ids)

        if matched > 0:
            return self._scoring.entity_match_weight * matched

        return 0.0

    def _compute_citation_score(self, story: Story) -> float:
        """Compute citation-based score from Semantic Scholar data.

        Uses log normalization: log(1 + citations) / log(1 + cap)
        to prevent high-citation papers from dominating.

        Args:
            story: Story to score.

        Returns:
            Citation score component.
        """
        citation_count = 0

        # Look for citation data in raw items
        for item in story.raw_items:
            try:
                raw = json.loads(item.raw_json)
                if "citation_count" in raw:
                    citation_count = max(citation_count, int(raw["citation_count"]))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue

        if citation_count <= 0:
            return 0.0

        cap = self._scoring.citation_normalization_cap
        normalized = math.log(1 + citation_count) / math.log(1 + cap)
        return min(normalized, 1.0) * self._scoring.citation_weight

    def _compute_cross_source_score(self, story: Story) -> float:
        """Compute cross-source quality signal score.

        Adds bonus when the story appears in quality signal sources
        like Papers With Code or HuggingFace Daily Papers.

        Args:
            story: Story to score.

        Returns:
            Cross-source score component (capped at CROSS_SOURCE_SCORE_CAP).
        """
        matched_sources: set[str] = set()

        # Check source IDs of all items
        for item in story.raw_items:
            # Check if the source is a quality signal source
            if item.source_id in QUALITY_SIGNAL_SOURCES:
                matched_sources.add(item.source_id)
                continue

            # Also check raw_json for quality signal flags
            try:
                raw = json.loads(item.raw_json)
                for source in QUALITY_SIGNAL_SOURCES:
                    if raw.get(f"from_{source}"):
                        matched_sources.add(source)
            except (json.JSONDecodeError, KeyError):
                continue

        if not matched_sources:
            return 0.0

        score = len(matched_sources) * self._scoring.cross_source_weight
        return min(score, CROSS_SOURCE_SCORE_CAP)

    def _compute_llm_relevance_score(self, story: Story) -> float:
        """Compute LLM-based relevance score.

        Looks up the pre-computed LLM relevance score for this story
        and applies the configured weight. Returns 0.0 when no LLM
        score is available (graceful degradation).

        Args:
            story: Story to score.

        Returns:
            LLM relevance score component.
        """
        raw_score = self._llm_scores.get(story.story_id, 0.0)
        return raw_score * self._scoring.llm_relevance_weight

    def _compute_semantic_score(self, story: Story) -> float:
        """Compute embedding-based semantic similarity score.

        Uses the SemanticScorer to compare story text against topic
        embeddings. Falls back to 0.0 when fastembed is unavailable.

        Args:
            story: Story to score.

        Returns:
            Semantic score component.
        """
        if self._semantic_scorer is None:
            return 0.0

        # Build text from title + abstracts
        text = story.title
        for item in story.raw_items:
            abstract = self._extract_abstract(item)
            if abstract:
                text += " " + abstract

        return self._semantic_scorer.score_text_weighted(
            text, self._scoring.semantic_match_weight
        )


def score_stories_pure(
    stories: list[Story],
    config: ScorerConfig,
    run_id: str = "pure",
) -> list[ScoredStory]:
    """Pure function API for scoring stories.

    Args:
        stories: Stories to score.
        config: Scorer configuration bundle.
        run_id: Run identifier.

    Returns:
        List of ScoredStory objects.
    """
    scorer = StoryScorer(run_id=run_id, config=config)
    return scorer.score_stories(stories)
