"""Worth reading ranker module for digest output constraints.

This module provides deterministic ranking, quotas, and source throttling
for the digest output. It enforces Top 5, per-source caps, and radar max
constraints while prioritizing frontier topics and first-hand sources.
"""

from src.ranker.models import (
    DroppedEntry,
    RankerOutput,
    RankerResult,
    RankerSummary,
    ScoreComponents,
    ScoredStory,
)
from src.ranker.ranker import StoryRanker, rank_stories_pure
from src.ranker.state_machine import RankerState, RankerStateMachine
from src.ranker.topic_matcher import TopicMatch, TopicMatcher


__all__ = [
    "DroppedEntry",
    "RankerOutput",
    "RankerResult",
    "RankerState",
    "RankerStateMachine",
    "RankerSummary",
    "ScoreComponents",
    "ScoredStory",
    "StoryRanker",
    "TopicMatch",
    "TopicMatcher",
    "rank_stories_pure",
]
