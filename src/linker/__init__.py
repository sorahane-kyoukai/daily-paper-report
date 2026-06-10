"""Story linker for cross-source deduplication and link aggregation."""

from src.linker.linker import StoryLinker
from src.linker.models import (
    CandidateGroup,
    EntityID,
    LinkerResult,
    MergeRationale,
    SourceID,
    Story,
    StoryID,
    StoryLink,
    TaggedItem,
)
from src.linker.state_machine import LinkerState, LinkerStateMachine


__all__ = [
    "CandidateGroup",
    "EntityID",
    "LinkerResult",
    "LinkerState",
    "LinkerStateMachine",
    "MergeRationale",
    "SourceID",
    "Story",
    "StoryID",
    "StoryLink",
    "StoryLinker",
    "TaggedItem",
]
