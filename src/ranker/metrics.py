"""Metrics collection for the ranker module."""

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class RankerMetrics:
    """Metrics for ranker operations.

    Attributes:
        stories_in: Number of input stories.
        stories_out: Number of output stories.
        dropped_total: Total stories dropped.
        dropped_by_source: Dropped count per source.
        score_values: All scores for percentile calculation.
        top5_count: Stories in top5.
        radar_count: Stories in radar.
        scoring_duration_ms: Time spent scoring.
        quota_duration_ms: Time spent on quota filtering.
    """

    stories_in: int = 0
    stories_out: int = 0
    dropped_total: int = 0
    dropped_by_source: dict[str, int] = field(default_factory=dict)
    score_values: list[float] = field(default_factory=list)
    top5_count: int = 0
    radar_count: int = 0
    scoring_duration_ms: float = 0.0
    quota_duration_ms: float = 0.0

    _instance: ClassVar["RankerMetrics | None"] = None

    @classmethod
    def get_instance(cls) -> "RankerMetrics":
        """Get singleton metrics instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset metrics (primarily for testing)."""
        cls._instance = None

    def record_stories_in(self, count: int) -> None:
        """Record input story count.

        Args:
            count: Number of input stories.
        """
        self.stories_in = count

    def record_stories_out(self, count: int) -> None:
        """Record output story count.

        Args:
            count: Number of output stories.
        """
        self.stories_out = count

    def record_drop(self, source_id: str) -> None:
        """Record a dropped story.

        Args:
            source_id: Source ID of the dropped story.
        """
        self.dropped_total += 1
        self.dropped_by_source[source_id] = self.dropped_by_source.get(source_id, 0) + 1

    def record_score(self, score: float) -> None:
        """Record a score for percentile calculation.

        Args:
            score: Score value.
        """
        self.score_values.append(score)

    def record_section_counts(self, top5: int, radar: int) -> None:
        """Record section counts.

        Args:
            top5: Number of stories in top5.
            radar: Number of stories in radar.
        """
        self.top5_count = top5
        self.radar_count = radar

    def record_scoring_duration(self, duration_ms: float) -> None:
        """Record scoring duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self.scoring_duration_ms = duration_ms

    def record_quota_duration(self, duration_ms: float) -> None:
        """Record quota filtering duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self.quota_duration_ms = duration_ms

    def get_score_percentiles(self) -> dict[str, float]:
        """Calculate score percentiles (p50/p90/p99).

        Returns:
            Dictionary with p50, p90, p99 values.
        """
        if not self.score_values:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0}

        sorted_scores = sorted(self.score_values)
        n = len(sorted_scores)

        def percentile(p: float) -> float:
            idx = int(p * n / 100)
            return sorted_scores[min(idx, n - 1)]

        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p99": percentile(99),
        }

    def to_dict(self) -> dict[str, object]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "stories_in": self.stories_in,
            "stories_out": self.stories_out,
            "dropped_total": self.dropped_total,
            "dropped_by_source": self.dropped_by_source,
            "top5_count": self.top5_count,
            "radar_count": self.radar_count,
            "scoring_duration_ms": self.scoring_duration_ms,
            "quota_duration_ms": self.quota_duration_ms,
            "score_percentiles": self.get_score_percentiles(),
        }
