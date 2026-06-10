"""Metrics for Story linker operations."""

from dataclasses import dataclass, field


@dataclass
class LinkerMetrics:
    """Metrics for linker operations.

    Tracks merge counts, story counts, and fallback ratios.
    """

    _instance: "LinkerMetrics | None" = field(default=None, repr=False, init=False)

    items_in: int = 0
    stories_out: int = 0
    merges_total: int = 0
    fallback_merges: int = 0

    @classmethod
    def get_instance(cls) -> "LinkerMetrics":
        """Get or create the singleton instance.

        Returns:
            LinkerMetrics instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance for testing."""
        cls._instance = None

    def record_items_in(self, count: int) -> None:
        """Record input item count.

        Args:
            count: Number of input items.
        """
        self.items_in = count

    def record_stories_out(self, count: int) -> None:
        """Record output story count.

        Args:
            count: Number of output stories.
        """
        self.stories_out = count

    def record_merge(self, is_fallback: bool = False) -> None:
        """Record a merge operation.

        Args:
            is_fallback: Whether this was a fallback merge.
        """
        self.merges_total += 1
        if is_fallback:
            self.fallback_merges += 1

    @property
    def fallback_ratio(self) -> float:
        """Calculate fallback merge ratio.

        Returns:
            Ratio of fallback merges (0.0-1.0).
        """
        if self.merges_total == 0:
            return 0.0
        return self.fallback_merges / self.merges_total

    def to_dict(self) -> dict[str, object]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary of metric values.
        """
        return {
            "items_in": self.items_in,
            "stories_out": self.stories_out,
            "merges_total": self.merges_total,
            "fallback_merges": self.fallback_merges,
            "fallback_ratio": round(self.fallback_ratio, 4),
        }
