"""Tests for HTML profile utilities."""

import re

from src.collectors.html_profile.utils import (
    RegexCache,
    compile_patterns,
    compile_regex,
)


class TestCompileRegex:
    """Tests for compile_regex function."""

    def test_compiles_pattern(self) -> None:
        """Test that pattern is compiled correctly."""
        pattern = compile_regex(r"\d{4}-\d{2}-\d{2}")
        assert pattern.match("2024-01-15")
        assert not pattern.match("not a date")

    def test_caches_result(self) -> None:
        """Test that same pattern returns cached result."""
        pattern1 = compile_regex(r"\d+")
        pattern2 = compile_regex(r"\d+")
        assert pattern1 is pattern2

    def test_different_patterns_not_cached_together(self) -> None:
        """Test that different patterns are cached separately."""
        pattern1 = compile_regex(r"\d+")
        pattern2 = compile_regex(r"\w+")
        assert pattern1 is not pattern2

    def test_flags_affect_caching(self) -> None:
        """Test that patterns with different flags are cached separately."""
        pattern1 = compile_regex(r"test", 0)
        pattern2 = compile_regex(r"test", re.IGNORECASE)
        assert pattern1 is not pattern2


class TestCompilePatterns:
    """Tests for compile_patterns function."""

    def test_compiles_list_of_patterns(self) -> None:
        """Test that list of patterns is compiled correctly."""
        patterns = compile_patterns([r"\d+", r"\w+"])
        assert len(patterns) == 2
        assert patterns[0].match("123")
        assert patterns[1].match("abc")

    def test_empty_list(self) -> None:
        """Test that empty list returns empty list."""
        patterns = compile_patterns([])
        assert patterns == []


class TestRegexCache:
    """Tests for RegexCache class."""

    def test_get_compiles_and_caches(self) -> None:
        """Test that get() compiles and caches patterns."""
        cache = RegexCache()
        pattern1 = cache.get(r"\d+")
        pattern2 = cache.get(r"\d+")
        assert pattern1 is pattern2
        assert len(cache) == 1

    def test_compile_all(self) -> None:
        """Test that compile_all() compiles all patterns."""
        cache = RegexCache()
        patterns = cache.compile_all([r"\d+", r"\w+", r"\s+"])
        assert len(patterns) == 3
        assert len(cache) == 3

    def test_clear(self) -> None:
        """Test that clear() removes all cached patterns."""
        cache = RegexCache()
        cache.compile_all([r"\d+", r"\w+"])
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_flags_work(self) -> None:
        """Test that flags are applied correctly."""
        cache = RegexCache()
        pattern = cache.get(r"test", re.IGNORECASE)
        assert pattern.match("TEST")
        assert pattern.match("test")
