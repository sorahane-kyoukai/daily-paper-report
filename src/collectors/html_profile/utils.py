"""Utilities for HTML profile parsing.

This module provides shared utilities including regex caching
and common parsing helpers.
"""

import re
from functools import lru_cache
from re import Pattern


@lru_cache(maxsize=128)
def compile_regex(pattern: str, flags: int = 0) -> Pattern[str]:
    """Compile a regex pattern with caching.

    Uses LRU cache to avoid recompiling the same pattern multiple times.
    This improves performance when the same patterns are used repeatedly
    across multiple extraction calls.

    Args:
        pattern: Regex pattern string.
        flags: Regex flags (e.g., re.IGNORECASE).

    Returns:
        Compiled regex pattern object.
    """
    return re.compile(pattern, flags)


def compile_patterns(patterns: list[str], flags: int = 0) -> list[Pattern[str]]:
    """Compile a list of regex patterns with caching.

    Args:
        patterns: List of regex pattern strings.
        flags: Regex flags to apply to all patterns.

    Returns:
        List of compiled regex pattern objects.
    """
    return [compile_regex(pattern, flags) for pattern in patterns]


class RegexCache:
    """Cache for compiled regex patterns with instance-level scope.

    This class provides a way to compile and cache regex patterns
    at the instance level, useful when patterns are configuration-driven
    and may vary between instances.
    """

    def __init__(self) -> None:
        """Initialize the regex cache."""
        self._cache: dict[tuple[str, int], Pattern[str]] = {}

    def get(self, pattern: str, flags: int = 0) -> Pattern[str]:
        """Get a compiled regex pattern from cache or compile it.

        Args:
            pattern: Regex pattern string.
            flags: Regex flags.

        Returns:
            Compiled regex pattern object.
        """
        key = (pattern, flags)
        if key not in self._cache:
            self._cache[key] = re.compile(pattern, flags)
        return self._cache[key]

    def compile_all(
        self,
        patterns: list[str],
        flags: int = 0,
    ) -> list[Pattern[str]]:
        """Compile and cache all patterns.

        Args:
            patterns: List of regex pattern strings.
            flags: Regex flags to apply to all patterns.

        Returns:
            List of compiled regex pattern objects.
        """
        return [self.get(pattern, flags) for pattern in patterns]

    def clear(self) -> None:
        """Clear all cached patterns."""
        self._cache.clear()

    def __len__(self) -> int:
        """Return the number of cached patterns."""
        return len(self._cache)
