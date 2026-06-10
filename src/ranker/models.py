"""Data models for the Story ranker."""

from dataclasses import dataclass, field
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.linker.models import Story, StorySection


@dataclass(frozen=True)
class ScoreComponents:
    """Breakdown of a story's score into components.

    Attributes:
        tier_score: Score contribution from source tier.
        kind_score: Score contribution from content kind.
        topic_score: Score contribution from topic keyword matches.
        recency_score: Score contribution from recency decay.
        entity_score: Score contribution from entity matches.
        citation_score: Score contribution from citation count (Semantic Scholar).
        cross_source_score: Score contribution from cross-source signals.
        semantic_score: Score contribution from embedding-based semantic matching.
        llm_relevance_score: Score contribution from LLM-based relevance evaluation.
        total_score: Sum of all components.
    """

    tier_score: float
    kind_score: float
    topic_score: float
    recency_score: float
    entity_score: float
    citation_score: float = 0.0
    cross_source_score: float = 0.0
    semantic_score: float = 0.0
    llm_relevance_score: float = 0.0
    total_score: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary of component name to value.
        """
        return {
            "tier_score": self.tier_score,
            "kind_score": self.kind_score,
            "topic_score": self.topic_score,
            "recency_score": self.recency_score,
            "entity_score": self.entity_score,
            "citation_score": self.citation_score,
            "cross_source_score": self.cross_source_score,
            "semantic_score": self.semantic_score,
            "llm_relevance_score": self.llm_relevance_score,
            "total_score": self.total_score,
        }


@dataclass
class ScoredStory:
    """A Story with its computed score and components.

    Attributes:
        story: The Story being scored.
        components: Score breakdown by component.
        assigned_section: Section this story is assigned to.
        dropped: Whether this story was dropped by quota.
        drop_reason: Reason for being dropped.
    """

    story: Story
    components: ScoreComponents
    assigned_section: StorySection | None = None
    dropped: bool = False
    drop_reason: str | None = None


@dataclass
class DroppedEntry:
    """Record of a story dropped by quota.

    Attributes:
        story_id: ID of the dropped story.
        source_id: Source ID of the dropped story.
        score: Score at time of drop.
        drop_reason: Why the story was dropped.
        arxiv_category: arXiv category if applicable.
    """

    story_id: str
    source_id: str
    score: float
    drop_reason: str
    arxiv_category: str | None = None


@dataclass
class EntityGroup:
    """Group of stories for a single entity.

    Attributes:
        entity_id: Entity identifier.
        entity_name: Human-readable entity name.
        stories: Stories belonging to this entity.
    """

    entity_id: str
    entity_name: str
    stories: list[Story] = field(default_factory=list)


class RankerOutput(BaseModel):
    """Output of the ranker with four ordered lists.

    Attributes:
        top5: Top 5 must-read stories.
        model_releases_by_entity: Model releases grouped by entity.
        papers: Papers section.
        radar: Worth monitoring section.
        score_map: Mapping of story_id to score breakdown for serialization.
        output_checksum: SHA-256 of the ordered output JSON.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    top5: list[Story] = Field(default_factory=list)
    model_releases_by_entity: dict[str, list[Story]] = Field(default_factory=dict)
    papers: list[Story] = Field(default_factory=list)
    radar: list[Story] = Field(default_factory=list)
    score_map: dict[str, dict[str, float]] = Field(default_factory=dict)
    output_checksum: str = ""


@dataclass
class DroppedStats:
    """Statistics about dropped stories.

    Attributes:
        total_dropped: Total number of stories dropped.
        by_source: Dropped count per source.
        by_reason: Dropped count per reason.
        by_arxiv_category: Dropped count per arXiv category.
    """

    total_dropped: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_reason: dict[str, int] = field(default_factory=dict)
    by_arxiv_category: dict[str, int] = field(default_factory=dict)


@dataclass
class RankerSummary:
    """Summary for STATE.md artifact.

    Attributes:
        run_id: Run identifier.
        stories_in: Number of input stories.
        top5_count: Number of stories in top5.
        radar_count: Number of stories in radar.
        papers_count: Number of papers.
        model_releases_count: Total model releases.
        dropped_stats: Statistics about dropped stories.
        top_topic_hits: Top topic matches.
        score_percentiles: p50/p90/p99 of scores.
        output_checksum: SHA-256 of output JSON.
    """

    run_id: str
    stories_in: int
    top5_count: int
    radar_count: int
    papers_count: int
    model_releases_count: int
    dropped_stats: DroppedStats
    top_topic_hits: dict[str, int] = field(default_factory=dict)
    score_percentiles: dict[str, float] = field(default_factory=dict)
    output_checksum: str = ""


class RankerResult(BaseModel):
    """Complete result of the ranking operation.

    Attributes:
        output: The four ordered output lists.
        summary: Summary statistics.
        dropped_entries: Details of dropped stories.
        scored_stories: All scored stories (for audit).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    output: Annotated[RankerOutput, Field(description="Ordered output sections")]
    stories_in: Annotated[int, Field(ge=0, description="Input story count")]
    stories_out: Annotated[int, Field(ge=0, description="Output story count")]
    dropped_total: Annotated[int, Field(ge=0, description="Total dropped count")]
    dropped_entries: list[DroppedEntry] = Field(default_factory=list)
    top_topic_hits: dict[str, int] = Field(default_factory=dict)
    score_percentiles: dict[str, float] = Field(default_factory=dict)
    output_checksum: str = ""
