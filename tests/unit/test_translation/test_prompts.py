"""Tests for translation prompt construction."""

from __future__ import annotations

from src.features.translation.prompts import (
    CURRENT_TRANSLATION_PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    build_translation_prompt,
)


class TestSystemInstruction:
    """Tests for the system instruction constant."""

    def test_mentions_traditional_chinese(self) -> None:
        assert "\u7e41\u9ad4\u4e2d\u6587" in SYSTEM_INSTRUCTION

    def test_mentions_preserve_technical_terms(self) -> None:
        assert "technical terms" in SYSTEM_INSTRUCTION.lower()

    def test_requires_json_array(self) -> None:
        assert "JSON array" in SYSTEM_INSTRUCTION

    def test_prompt_version_is_content_hash(self) -> None:
        assert CURRENT_TRANSLATION_PROMPT_VERSION.startswith("sha256:")
        assert len(CURRENT_TRANSLATION_PROMPT_VERSION) == len("sha256:") + 16


class TestBuildTranslationPrompt:
    """Tests for build_translation_prompt."""

    def test_single_story(self) -> None:
        stories = [
            {
                "story_id": "story-1",
                "title": "A Novel Transformer Architecture",
                "summary": "We propose a new attention mechanism.",
            }
        ]
        prompt = build_translation_prompt(stories)
        assert "story-1" in prompt
        assert "A Novel Transformer Architecture" in prompt
        assert "We propose a new attention mechanism." in prompt

    def test_multiple_stories(self) -> None:
        stories = [
            {"story_id": f"s{i}", "title": f"Title {i}", "summary": f"Summary {i}"}
            for i in range(3)
        ]
        prompt = build_translation_prompt(stories)
        for i in range(3):
            assert f"s{i}" in prompt
            assert f"Title {i}" in prompt

    def test_story_without_summary(self) -> None:
        stories = [{"story_id": "s1", "title": "Some Title", "summary": None}]
        prompt = build_translation_prompt(stories)
        assert "s1" in prompt
        assert "Some Title" in prompt
        assert "Summary:" not in prompt

    def test_story_with_empty_summary(self) -> None:
        stories = [{"story_id": "s1", "title": "Title", "summary": ""}]
        prompt = build_translation_prompt(stories)
        assert "Summary:" not in prompt

    def test_includes_output_format(self) -> None:
        stories = [{"story_id": "s1", "title": "T"}]
        prompt = build_translation_prompt(stories)
        assert "title_zh" in prompt
        assert "summary_zh" in prompt
        assert "220-320" in prompt
        assert "2-4 complete sentences" in prompt
        assert "。" in prompt

    def test_preserves_technical_terms_example(self) -> None:
        stories = [{"story_id": "s1", "title": "T"}]
        prompt = build_translation_prompt(stories)
        assert "Transformer" in prompt
