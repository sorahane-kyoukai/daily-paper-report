"""Main Story ranker orchestrator."""

import hashlib
import json
import time
from datetime import UTC, datetime

import structlog

from src.features.config.schemas.entities import EntitiesConfig
from src.features.config.schemas.topics import TopicsConfig
from src.linker.models import Story, StorySection
from src.ranker.metrics import RankerMetrics
from src.ranker.models import DroppedEntry, RankerOutput, RankerResult, ScoredStory
from src.ranker.quota import QuotaFilter
from src.ranker.scorer import ScorerConfig, StoryScorer
from src.ranker.state_machine import RankerState, RankerStateMachine
from src.ranker.topic_matcher import TopicMatcher


logger = structlog.get_logger()


class StoryRanker:
    """Orchestrates Story ranking with scoring, quotas, and section assignment.

    Implements a state machine flow:
        STORIES_FINAL -> SCORED -> QUOTA_FILTERED -> ORDERED_OUTPUTS

    Produces four output sections:
        - top5: Top 5 must-read stories
        - model_releases_by_entity: Model releases grouped by entity
        - papers: Papers section
        - radar: Worth monitoring section
    """

    def __init__(  # noqa: PLR0913
        self,
        run_id: str,
        topics_config: TopicsConfig | None = None,
        entities_config: EntitiesConfig | None = None,
        metrics: RankerMetrics | None = None,
        now: datetime | None = None,
        llm_scores: dict[str, float] | None = None,
    ) -> None:
        """Initialize the ranker.

        Args:
            run_id: Run identifier for logging and state.
            topics_config: Topics configuration with scoring/quotas.
            entities_config: Entities configuration.
            metrics: Optional metrics instance.
            now: Current time for recency calculation.
            llm_scores: Pre-computed LLM relevance scores (story_id -> float).
        """
        self._run_id = run_id
        self._topics_config = topics_config or TopicsConfig()
        self._entities_config = entities_config
        self._now = now or datetime.now(UTC)
        self._llm_scores = llm_scores or {}

        self._scoring_config = self._topics_config.scoring
        self._quotas_config = self._topics_config.quotas

        self._metrics = metrics or RankerMetrics.get_instance()
        self._state_machine = RankerStateMachine(run_id)

        self._log = logger.bind(
            component="ranker",
            run_id=run_id,
        )

        # Extract entity IDs for scoring
        self._entity_ids: list[str] = []
        if entities_config:
            self._entity_ids = [e.id for e in entities_config.entities]

        # Pre-compile topic patterns for topic hit counting
        self._topic_matcher = TopicMatcher(list(self._topics_config.topics))

    @property
    def state(self) -> RankerState:
        """Get current ranker state."""
        return self._state_machine.state

    def rank_stories(self, stories: list[Story]) -> RankerResult:
        """Rank stories and produce ordered output sections.

        This is the main entry point for the ranker.

        Args:
            stories: Stories to rank (from linker).

        Returns:
            RankerResult with output sections and statistics.
        """
        self._log.info(
            "ranker_started",
            stories_in=len(stories),
        )
        self._metrics.record_stories_in(len(stories))

        if not stories:
            self._transition_through_all_states()
            return self._empty_result()

        # Phase 1: Score all stories
        start_score = time.perf_counter()
        scored = self._score_stories(stories)
        self._state_machine.to_scored()
        scoring_ms = (time.perf_counter() - start_score) * 1000
        self._metrics.record_scoring_duration(scoring_ms)

        # Record scores for metrics
        for s in scored:
            self._metrics.record_score(s.components.total_score)

        # Phase 2: Apply quotas
        start_quota = time.perf_counter()
        sections, dropped = self._apply_quotas(scored)
        self._state_machine.to_quota_filtered()
        quota_ms = (time.perf_counter() - start_quota) * 1000
        self._metrics.record_quota_duration(quota_ms)

        # Phase 3: Build ordered outputs
        output = self._build_output(sections)
        self._state_machine.to_ordered_outputs()

        # Calculate statistics
        total_out = (
            len(output.top5)
            + sum(len(v) for v in output.model_releases_by_entity.values())
            + len(output.papers)
            + len(output.radar)
        )

        self._metrics.record_stories_out(total_out)
        self._metrics.record_section_counts(len(output.top5), len(output.radar))

        # Record drops
        for d in dropped:
            self._metrics.record_drop(d.source_id)

        # Calculate topic hits
        topic_hits = self._count_topic_hits(scored)

        result = RankerResult(
            output=output,
            stories_in=len(stories),
            stories_out=total_out,
            dropped_total=len(dropped),
            dropped_entries=dropped,
            top_topic_hits=topic_hits,
            score_percentiles=self._metrics.get_score_percentiles(),
            output_checksum=output.output_checksum,
        )

        self._log.info(
            "ranker_complete",
            stories_in=len(stories),
            top5_count=len(output.top5),
            radar_count=len(output.radar),
            dropped_total=len(dropped),
        )

        return result

    def _transition_through_all_states(self) -> None:
        """Transition through all states for empty input."""
        self._state_machine.to_scored()
        self._state_machine.to_quota_filtered()
        self._state_machine.to_ordered_outputs()

    def _empty_result(self) -> RankerResult:
        """Create empty result for no input."""
        empty_output = RankerOutput(
            top5=[],
            model_releases_by_entity={},
            papers=[],
            radar=[],
            score_map={},
            output_checksum=self._compute_checksum([]),
        )
        return RankerResult(
            output=empty_output,
            stories_in=0,
            stories_out=0,
            dropped_total=0,
        )

    def _score_stories(self, stories: list[Story]) -> list[ScoredStory]:
        """Score all stories.

        Args:
            stories: Stories to score.

        Returns:
            List of scored stories.
        """
        config = ScorerConfig(
            scoring_config=self._scoring_config,
            topics=list(self._topics_config.topics),
            entity_ids=self._entity_ids,
            now=self._now,
            llm_scores=self._llm_scores,
        )
        scorer = StoryScorer(run_id=self._run_id, config=config)
        return scorer.score_stories(stories)

    def _apply_quotas(
        self, scored: list[ScoredStory]
    ) -> tuple[dict[StorySection, list[ScoredStory]], list[DroppedEntry]]:
        """Apply quota filtering.

        Args:
            scored: Scored stories.

        Returns:
            Tuple of (sections dict, dropped entries).
        """
        quota_filter = QuotaFilter(
            run_id=self._run_id,
            quotas_config=self._quotas_config,
            llm_relevance_weight=self._scoring_config.llm_relevance_weight,
        )
        kept, _dropped = quota_filter.apply_quotas(scored)
        sections = quota_filter.assign_sections(kept)
        return sections, quota_filter.dropped_entries

    def _build_output(
        self, sections: dict[StorySection, list[ScoredStory]]
    ) -> RankerOutput:
        """Build final output from sections.

        Args:
            sections: Section -> ScoredStory mapping.

        Returns:
            RankerOutput with ordered lists.
        """
        top5 = [s.story for s in sections.get(StorySection.TOP5, [])]
        papers = [s.story for s in sections.get(StorySection.PAPERS, [])]
        radar = [s.story for s in sections.get(StorySection.RADAR, [])]

        # Build score_map from all scored stories
        llm_weight = self._scoring_config.llm_relevance_weight
        score_map: dict[str, dict[str, float]] = {}
        for section_stories in sections.values():
            for scored in section_stories:
                entry = scored.components.to_dict()
                if llm_weight > 0:
                    entry["llm_raw_score"] = entry["llm_relevance_score"] / llm_weight
                score_map[scored.story.story_id] = entry

        # Group model releases by entity
        model_releases_by_entity: dict[str, list[Story]] = {}
        for s in sections.get(StorySection.MODEL_RELEASES, []):
            for entity_id in s.story.entities:
                if entity_id not in model_releases_by_entity:
                    model_releases_by_entity[entity_id] = []
                model_releases_by_entity[entity_id].append(s.story)
                break  # Only assign to first entity

            # If no entities, put under "other"
            if not s.story.entities:
                if "other" not in model_releases_by_entity:
                    model_releases_by_entity["other"] = []
                model_releases_by_entity["other"].append(s.story)

        # Compute checksum over all stories for idempotency verification
        all_stories = (
            top5
            + papers
            + radar
            + [s for stories in model_releases_by_entity.values() for s in stories]
        )
        checksum = self._compute_checksum(all_stories)

        return RankerOutput(
            top5=top5,
            model_releases_by_entity=model_releases_by_entity,
            papers=papers,
            radar=radar,
            score_map=score_map,
            output_checksum=checksum,
        )

    def _compute_checksum(self, stories: list[Story]) -> str:
        """Compute SHA-256 checksum of ordered output.

        Args:
            stories: All stories in output order.

        Returns:
            SHA-256 hex digest.
        """
        # Build deterministic JSON representation
        data = [story.to_json_dict() for story in stories]
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _count_topic_hits(self, scored: list[ScoredStory]) -> dict[str, int]:
        """Count topic keyword hits across scored stories.

        Uses pre-compiled TopicMatcher for efficient matching.

        Args:
            scored: Scored stories.

        Returns:
            Dictionary of topic name -> hit count.
        """
        topic_hits: dict[str, int] = {}

        for s in scored:
            text = s.story.title.lower()
            matches = self._topic_matcher.count_matches(text)
            for topic_name, count in matches.items():
                topic_hits[topic_name] = topic_hits.get(topic_name, 0) + count

        return topic_hits


def rank_stories_pure(  # noqa: PLR0913
    stories: list[Story],
    topics_config: TopicsConfig | None = None,
    entities_config: EntitiesConfig | None = None,
    now: datetime | None = None,
    run_id: str = "pure",
    llm_scores: dict[str, float] | None = None,
) -> RankerResult:
    """Pure function API for Story ranking.

    Args:
        stories: Stories to rank.
        topics_config: Topics configuration.
        entities_config: Entities configuration.
        now: Current time for recency calculation.
        run_id: Run identifier.
        llm_scores: Pre-computed LLM relevance scores (story_id -> float).

    Returns:
        RankerResult with output sections.
    """
    ranker = StoryRanker(
        run_id=run_id,
        topics_config=topics_config,
        entities_config=entities_config,
        now=now,
        llm_scores=llm_scores,
    )
    return ranker.rank_stories(stories)
