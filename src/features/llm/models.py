"""Data models for LLM requests and responses."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LlmRelevanceResult:
    """Result of LLM relevance evaluation for a single story.

    Attributes:
        story_id: Identifier of the evaluated story.
        relevance_score: Relevance score from 0.0 to 1.0.
        rationale: Short explanation of the score.
        topics_matched: Which configured topics matched.
    """

    story_id: str
    relevance_score: float
    rationale: str
    topics_matched: list[str]


@dataclass
class LlmPhaseResult:
    """Aggregated result of the LLM evaluation phase.

    Attributes:
        scores: Mapping of story_id to relevance_score.
        results: Full results for audit trail.
        stories_evaluated: Number of stories successfully evaluated.
        stories_skipped: Number of stories skipped (non-paper, no abstract).
        api_calls_made: Total API calls made during the phase.
        errors: List of error messages encountered.
    """

    scores: dict[str, float] = field(default_factory=dict)
    results: list[LlmRelevanceResult] = field(default_factory=list)
    stories_evaluated: int = 0
    stories_skipped: int = 0
    api_calls_made: int = 0
    errors: list[str] = field(default_factory=list)
