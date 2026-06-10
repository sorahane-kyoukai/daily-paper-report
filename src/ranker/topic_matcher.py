"""Topic keyword matching utility for story ranking.

This module provides a reusable TopicMatcher class that pre-compiles
regex patterns for efficient topic keyword matching across stories.
"""

import re
from dataclasses import dataclass, field

from src.features.config.schemas.topics import TopicConfig


# Keywords this short are prone to substring false positives
# (e.g. "RL" in "URL", "QA" in "QUALITY"), so they get \b guards.
_SHORT_KEYWORD_THRESHOLD = 4


@dataclass(frozen=True)
class TopicMatch:
    """Result of a topic match operation.

    Attributes:
        topic_name: Name of the matched topic.
        boost_weight: Boost weight for this topic.
        matched_keyword: The keyword that matched.
    """

    topic_name: str
    boost_weight: float
    matched_keyword: str


@dataclass
class CompiledTopic:
    """A topic with pre-compiled regex patterns.

    Attributes:
        config: Original topic configuration.
        patterns: Compiled regex patterns for each keyword.
    """

    config: TopicConfig
    patterns: list[re.Pattern[str]] = field(default_factory=list)


_WORD_CHARS_ONLY = re.compile(r"^\w+$")


def _compile_keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Compile a keyword into a regex pattern.

    Short all-word-character keywords (≤ _SHORT_KEYWORD_THRESHOLD chars)
    get word-boundary anchors to prevent false positives (e.g. "RL"
    matching "URL"). Keywords containing non-word characters (like "c++",
    ".net") or longer keywords use plain substring matching.

    Args:
        keyword: Raw keyword string from topic config.

    Returns:
        Compiled regex pattern.
    """
    escaped = re.escape(keyword)
    if len(keyword) <= _SHORT_KEYWORD_THRESHOLD and _WORD_CHARS_ONLY.match(keyword):
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


class TopicMatcher:
    """Matches text against topic keywords using pre-compiled patterns.

    Pre-compiles regex patterns on initialization for efficient
    repeated matching operations.
    """

    def __init__(self, topics: list[TopicConfig]) -> None:
        """Initialize the matcher with topic configurations.

        Args:
            topics: List of topic configurations to match against.
        """
        self._compiled_topics: list[CompiledTopic] = []

        for topic in topics:
            patterns = [_compile_keyword_pattern(kw) for kw in topic.keywords]
            self._compiled_topics.append(CompiledTopic(config=topic, patterns=patterns))

    @property
    def topic_count(self) -> int:
        """Get number of configured topics."""
        return len(self._compiled_topics)

    def match_text(self, text: str) -> list[TopicMatch]:
        """Find all topic matches in the given text.

        Each topic is matched at most once (first matching keyword wins).

        Args:
            text: Text to search for topic keywords.

        Returns:
            List of TopicMatch results for matched topics.
        """
        matches: list[TopicMatch] = []
        text_lower = text.lower()

        for compiled in self._compiled_topics:
            for pattern in compiled.patterns:
                if pattern.search(text_lower):
                    matches.append(
                        TopicMatch(
                            topic_name=compiled.config.name,
                            boost_weight=compiled.config.boost_weight,
                            matched_keyword=pattern.pattern.replace("\\", ""),
                        )
                    )
                    break  # Only count each topic once

        return matches

    def count_matches(self, text: str) -> dict[str, int]:
        """Count topic matches by topic name.

        Args:
            text: Text to search for topic keywords.

        Returns:
            Dictionary of topic name -> match count (0 or 1).
        """
        matches = self.match_text(text)
        return {m.topic_name: 1 for m in matches}

    def compute_boost_score(self, text: str, topic_match_weight: float) -> float:
        """Compute total boost score from topic matches.

        Args:
            text: Text to search for topic keywords.
            topic_match_weight: Multiplier for topic boost weights.

        Returns:
            Sum of (boost_weight * topic_match_weight) for all matches.
        """
        matches = self.match_text(text)
        return sum(m.boost_weight * topic_match_weight for m in matches)
