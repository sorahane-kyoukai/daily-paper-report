"""Topics configuration schema."""

from typing import Annotated

from pydantic import Field, model_validator

from src.data_model import StrictBaseModel
from src.features.config.schemas.base import LinkType


class DedupeConfig(StrictBaseModel):
    """Deduplication configuration.

    Attributes:
        canonical_url_strip_params: URL parameters to strip for canonicalization.
    """

    canonical_url_strip_params: list[str] = Field(default_factory=list)


class ScoringConfig(StrictBaseModel):
    """Scoring weights configuration.

    Attributes:
        tier_0_weight: Weight for Tier 0 sources.
        tier_1_weight: Weight for Tier 1 sources.
        tier_2_weight: Weight for Tier 2 sources.
        topic_match_weight: Weight for topic keyword matches.
        entity_match_weight: Weight for entity matches.
        recency_decay_factor: Decay factor for older items.
        citation_weight: Weight for citation count contribution.
        citation_normalization_cap: Cap for citation normalization (log scale).
        cross_source_weight: Weight per quality signal source matched.
        semantic_match_weight: Weight for embedding-based semantic similarity.
        semantic_similarity_threshold: Minimum cosine similarity to count as a match.
        llm_relevance_weight: Weight for LLM-based relevance scoring.
    """

    tier_0_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 3.0
    tier_1_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 2.0
    tier_2_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 1.0
    topic_match_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 1.5
    entity_match_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 2.0
    recency_decay_factor: Annotated[float, Field(ge=0.0, le=5.0)] = 0.1
    citation_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 0.5
    citation_normalization_cap: Annotated[int, Field(ge=1, le=100000)] = 1000
    cross_source_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 1.0
    semantic_match_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 1.0
    semantic_similarity_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.50
    llm_relevance_weight: Annotated[float, Field(ge=0.0, le=30.0)] = 10.0
    topic_score_cap: Annotated[float, Field(ge=0.0, le=100.0)] = 6.0


class TopicConfig(StrictBaseModel):
    """Configuration for a single topic.

    Attributes:
        name: Topic name.
        keywords: Keywords for matching (at least 1).
        boost_weight: Additional score boost for this topic.
    """

    name: Annotated[str, Field(min_length=1, max_length=100)]
    keywords: Annotated[list[str], Field(min_length=1)]
    boost_weight: Annotated[float, Field(ge=0.0, le=5.0)] = 1.0

    @model_validator(mode="after")
    def validate_keywords_non_empty(self) -> "TopicConfig":
        """Ensure keywords list contains non-empty strings."""
        for keyword in self.keywords:
            if not keyword.strip():
                msg = "Keywords must be non-empty strings"
                raise ValueError(msg)
        return self


class QuotasConfig(StrictBaseModel):
    """Output quotas configuration.

    Attributes:
        top5_max: Maximum items in Top 5.
        radar_max: Maximum items in Radar.
        per_source_max: Maximum items per source.
        arxiv_per_category_max: Maximum arXiv items per category.
        papers_max: Maximum items in Papers section.
        paper_exclusion_keywords: Case-insensitive keywords used to exclude
            paper-like stories from selection before section assignment.
        llm_bypass_threshold: Raw LLM score (0-1) above which papers bypass
            the arxiv_per_category_max quota. Set to 1.0 to disable.
    """

    top5_max: Annotated[int, Field(ge=0)] = 5
    radar_max: Annotated[int, Field(ge=0)] = 10
    per_source_max: Annotated[int, Field(ge=0)] = 10
    arxiv_per_category_max: Annotated[int, Field(ge=0)] = 10
    papers_max: Annotated[int, Field(ge=0)] = 20
    paper_exclusion_keywords: list[str] = Field(
        default_factory=lambda: [
            "medical",
            "clinical",
            "healthcare",
            "health care",
            "biomedical",
            "biomedicine",
            "medicine",
            "patient",
            "patients",
            "hospital",
            "diagnosis",
            "diagnostic",
            "disease",
            "diseases",
            "medical imaging",
            "drug discovery",
        ]
    )
    llm_bypass_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0

    @model_validator(mode="after")
    def validate_paper_exclusion_keywords(self) -> "QuotasConfig":
        """Ensure paper exclusion keywords are non-empty strings."""
        for keyword in self.paper_exclusion_keywords:
            if not keyword.strip():
                msg = "paper_exclusion_keywords must contain non-empty strings"
                raise ValueError(msg)
        return self


class TopicsConfig(StrictBaseModel):
    """Root configuration for topics.yaml.

    Attributes:
        version: Schema version.
        dedupe: Deduplication configuration.
        scoring: Scoring weights configuration.
        quotas: Output quotas configuration.
        topics: List of topic configurations.
        prefer_primary_link_order: Preferred link types for primary link selection.
    """

    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")] = "1.0"
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    quotas: QuotasConfig = Field(default_factory=QuotasConfig)
    topics: list[TopicConfig] = Field(default_factory=list)
    prefer_primary_link_order: list[LinkType] = Field(default_factory=list)
