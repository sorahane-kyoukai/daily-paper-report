"""Unit tests for LLM prompt building."""

import json

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.topics import TopicConfig
from src.features.llm.prompts import (
    build_batch_prompt,
    build_topics_section,
)
from src.features.store.models import DateConfidence, Item
from src.linker.models import Story, StoryLink


def _make_story(
    story_id: str = "test-1",
    title: str = "Test Paper",
    abstract: str | None = None,
) -> Story:
    """Create a test story with optional abstract."""
    raw_json = "{}"
    if abstract:
        raw_json = json.dumps({"abstract_snippet": abstract})

    item = Item(
        url="https://arxiv.org/abs/2401.00001",
        source_id="arxiv-rss",
        tier=0,
        kind="paper",
        title=title,
        content_hash="hash",
        raw_json=raw_json,
        date_confidence=DateConfidence.HIGH,
    )

    link = StoryLink(
        url="https://arxiv.org/abs/2401.00001",
        link_type=LinkType.ARXIV,
        source_id="arxiv-rss",
        tier=0,
        title=title,
    )

    return Story(
        story_id=story_id,
        title=title,
        primary_link=link,
        links=[link],
        raw_items=[item],
    )


class TestBuildTopicsSection:
    """Tests for build_topics_section."""

    def test_formats_single_topic(self) -> None:
        """Should format a single topic with keywords."""
        topics = [TopicConfig(name="LLM", keywords=["GPT", "language model"])]
        result = build_topics_section(topics)
        assert "**LLM**" in result
        assert "GPT, language model" in result

    def test_formats_multiple_topics(self) -> None:
        """Should format multiple topics as list."""
        topics = [
            TopicConfig(name="LLM", keywords=["GPT"]),
            TopicConfig(name="Safety", keywords=["alignment", "RLHF"]),
        ]
        result = build_topics_section(topics)
        assert "**LLM**" in result
        assert "**Safety**" in result
        assert "alignment, RLHF" in result

    def test_empty_topics(self) -> None:
        """Should return empty string for no topics."""
        result = build_topics_section([])
        assert result == ""


class TestBuildBatchPrompt:
    """Tests for build_batch_prompt."""

    def test_includes_story_id_and_title(self) -> None:
        """Should include story ID and title in prompt."""
        story = _make_story(story_id="arxiv:2401.00001", title="GPT-5 Paper")
        topics = [TopicConfig(name="LLM", keywords=["GPT"])]

        prompt = build_batch_prompt([story], topics)

        assert "[arxiv:2401.00001]" in prompt
        assert "GPT-5 Paper" in prompt

    def test_includes_abstract_when_available(self) -> None:
        """Should include abstract in prompt when present."""
        story = _make_story(abstract="We propose a novel attention mechanism.")
        topics = [TopicConfig(name="LLM", keywords=["attention"])]

        prompt = build_batch_prompt([story], topics)

        assert "novel attention mechanism" in prompt
        assert "Abstract:" in prompt

    def test_omits_abstract_when_missing(self) -> None:
        """Should not include Abstract section when no abstract."""
        story = _make_story(abstract=None)
        topics = [TopicConfig(name="LLM", keywords=["GPT"])]

        prompt = build_batch_prompt([story], topics)

        assert "Abstract:" not in prompt

    def test_numbers_multiple_stories(self) -> None:
        """Should number stories in batch sequentially."""
        stories = [
            _make_story(story_id="s1", title="First"),
            _make_story(story_id="s2", title="Second"),
            _make_story(story_id="s3", title="Third"),
        ]
        topics = [TopicConfig(name="LLM", keywords=["test"])]

        prompt = build_batch_prompt(stories, topics)

        assert "1. [s1]" in prompt
        assert "2. [s2]" in prompt
        assert "3. [s3]" in prompt

    def test_includes_output_format_instructions(self) -> None:
        """Should include JSON output format instructions."""
        story = _make_story()
        topics = [TopicConfig(name="LLM", keywords=["test"])]

        prompt = build_batch_prompt([story], topics)

        assert "JSON array" in prompt
        assert '"score"' in prompt
        assert '"rationale"' in prompt
