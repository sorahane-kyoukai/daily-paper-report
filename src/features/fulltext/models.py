"""Models for full-paper content supplied to the curator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FullTextStatus(StrEnum):
    """Quality of the content available for one paper."""

    COMPLETE = "complete"
    COMPACTED = "compacted"
    PARTIAL = "partial"
    ABSTRACT_ONLY = "abstract_only"


CONFIDENCE_MULTIPLIERS: dict[FullTextStatus, float] = {
    FullTextStatus.COMPLETE: 1.0,
    FullTextStatus.COMPACTED: 0.95,
    FullTextStatus.PARTIAL: 0.92,
    FullTextStatus.ABSTRACT_ONLY: 0.85,
}


@dataclass(frozen=True)
class FullTextDocument:
    """Normalized full text and its provenance."""

    story_id: str
    text: str
    status: FullTextStatus
    source_url: str | None
    source_format: str
    sha256: str
    page_count: int = 0
    error: str | None = None

    @property
    def confidence_multiplier(self) -> float:
        """Return the scoring penalty associated with extraction quality."""
        return CONFIDENCE_MULTIPLIERS[self.status]
