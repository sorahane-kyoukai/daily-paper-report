"""Unit tests for LLM relevance processor."""

import json
from unittest.mock import MagicMock

import pytest

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.topics import TopicConfig
from src.features.llm.client import GeminiCodeAssistClient
from src.features.llm.errors import LlmApiError
from src.features.llm.processor import BATCH_SIZE, LlmRelevanceProcessor
from src.features.store.models import DateConfidence, Item
from src.linker.models import Story, StoryLink


def _make_story(
    story_id: str = "test-1",
    title: str = "Test Paper",
    abstract: str | None = "A novel approach to testing.",
    arxiv_id: str | None = "2401.00001",
) -> Story:
    """Create a test story."""
    raw_json = "{}"
    if abstract:
        raw_json = json.dumps({"abstract_snippet": abstract})

    item = Item(
        url=f"https://arxiv.org/abs/{arxiv_id or '0000.0000'}",
        source_id="arxiv-rss",
        tier=0,
        kind="paper",
        title=title,
        content_hash="hash",
        raw_json=raw_json,
        date_confidence=DateConfidence.HIGH,
    )

    link = StoryLink(
        url=f"https://arxiv.org/abs/{arxiv_id or '0000.0000'}",
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
        arxiv_id=arxiv_id,
    )


def _make_story_no_abstract(story_id: str = "no-abstract") -> Story:
    """Create a story without abstract or arxiv_id."""
    item = Item(
        url="https://example.com/blog",
        source_id="blog-source",
        tier=1,
        kind="blog",
        title="Blog Post",
        content_hash="hash",
        raw_json="{}",
        date_confidence=DateConfidence.LOW,
    )

    link = StoryLink(
        url="https://example.com/blog",
        link_type=LinkType.OFFICIAL,
        source_id="blog-source",
        tier=1,
        title="Blog Post",
    )

    return Story(
        story_id=story_id,
        title="Blog Post",
        primary_link=link,
        links=[link],
        raw_items=[item],
    )


def _make_processor(
    client: GeminiCodeAssistClient | None = None,
) -> LlmRelevanceProcessor:
    """Create a processor with mock client."""
    mock_client = client or MagicMock(spec=GeminiCodeAssistClient)
    topics = [TopicConfig(name="LLM", keywords=["language model", "GPT"])]
    return LlmRelevanceProcessor(client=mock_client, topics=topics)


class TestEvaluateStories:
    """Tests for LlmRelevanceProcessor.evaluate_stories."""

    def test_evaluates_stories_with_abstracts(self) -> None:
        """Should evaluate stories that have abstracts."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.return_value = json.dumps(
            [
                {
                    "id": "test-1",
                    "score": 0.9,
                    "rationale": "Highly relevant.",
                    "topics": ["LLM"],
                }
            ]
        )

        processor = _make_processor(mock_client)
        stories = [_make_story()]
        result = processor.evaluate_stories(stories)

        assert result.stories_evaluated == 1
        assert result.stories_skipped == 0
        assert result.scores["test-1"] == pytest.approx(0.9)
        assert len(result.results) == 1
        assert result.results[0].rationale == "Highly relevant."

    def test_skips_stories_without_abstracts(self) -> None:
        """Should skip stories lacking abstracts and arxiv_id."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        processor = _make_processor(mock_client)

        stories = [_make_story_no_abstract()]
        result = processor.evaluate_stories(stories)

        assert result.stories_skipped == 1
        assert result.stories_evaluated == 0
        mock_client.generate_content.assert_not_called()

    def test_batches_stories(self) -> None:
        """Should batch stories into groups of BATCH_SIZE."""
        stories = [_make_story(story_id=f"s{i}") for i in range(BATCH_SIZE + 2)]

        mock_client = MagicMock(spec=GeminiCodeAssistClient)

        def generate_for_batch(prompt: str, **kwargs: object) -> str:
            # Return scores for all story IDs found in prompt
            results = []
            for i in range(BATCH_SIZE + 2):
                sid = f"s{i}"
                if sid in prompt:
                    results.append(
                        {"id": sid, "score": 0.7, "rationale": "ok", "topics": []}
                    )
            return json.dumps(results)

        mock_client.generate_content.side_effect = generate_for_batch

        processor = _make_processor(mock_client)
        result = processor.evaluate_stories(stories)

        # Should make 2 API calls: one for BATCH_SIZE, one for remaining 2
        assert result.api_calls_made == 2
        assert result.stories_evaluated == BATCH_SIZE + 2

    def test_graceful_degradation_on_api_error(self) -> None:
        """Should assign neutral scores when API call fails."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.side_effect = LlmApiError("Timeout")

        processor = _make_processor(mock_client)
        stories = [_make_story(story_id="fail-1")]
        result = processor.evaluate_stories(stories)

        assert result.scores["fail-1"] == pytest.approx(0.5)
        assert len(result.errors) == 1
        assert "API error" in result.errors[0]

    def test_graceful_degradation_on_parse_error(self) -> None:
        """Should assign neutral scores when response is not valid JSON."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.return_value = "not valid json at all"

        processor = _make_processor(mock_client)
        stories = [_make_story(story_id="parse-fail")]
        result = processor.evaluate_stories(stories)

        assert result.scores["parse-fail"] == pytest.approx(0.5)
        assert len(result.errors) == 1

    def test_parse_error_splits_failed_batch(self) -> None:
        """Should split a malformed multi-story response before using neutral."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.side_effect = [
            "not valid json at all",
            json.dumps(
                [
                    {"id": "s0", "score": 0.8, "rationale": "ok", "topics": []},
                    {"id": "s1", "score": 0.7, "rationale": "ok", "topics": []},
                ]
            ),
            json.dumps(
                [
                    {"id": "s2", "score": 0.6, "rationale": "ok", "topics": []},
                    {"id": "s3", "score": 0.9, "rationale": "ok", "topics": []},
                ]
            ),
        ]

        processor = _make_processor(mock_client)
        stories = [_make_story(story_id=f"s{i}") for i in range(4)]
        result = processor.evaluate_stories(stories)

        assert result.stories_evaluated == 4
        assert result.errors == []
        assert result.api_calls_made == 3
        assert result.scores["s0"] == pytest.approx(0.8)
        assert result.scores["s3"] == pytest.approx(0.9)

    def test_empty_stories_returns_empty_result(self) -> None:
        """Should return empty result for no stories."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        processor = _make_processor(mock_client)
        result = processor.evaluate_stories([])

        assert result.stories_evaluated == 0
        assert result.stories_skipped == 0
        assert result.api_calls_made == 0

    def test_clamps_scores_to_valid_range(self) -> None:
        """Should clamp scores outside [0.0, 1.0]."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.return_value = json.dumps(
            [
                {"id": "test-1", "score": 1.5, "rationale": "over", "topics": []},
            ]
        )

        processor = _make_processor(mock_client)
        stories = [_make_story()]
        result = processor.evaluate_stories(stories)

        assert result.scores["test-1"] == pytest.approx(1.0)

    def test_handles_markdown_fenced_json(self) -> None:
        """Should parse JSON even with markdown code fences."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.return_value = '```json\n[{"id": "test-1", "score": 0.8, "rationale": "good", "topics": ["LLM"]}]\n```'

        processor = _make_processor(mock_client)
        stories = [_make_story()]
        result = processor.evaluate_stories(stories)

        assert result.scores["test-1"] == pytest.approx(0.8)

    def test_assigns_neutral_for_missing_story_ids(self) -> None:
        """Should assign 0.5 to stories not returned by LLM."""
        mock_client = MagicMock(spec=GeminiCodeAssistClient)
        mock_client.generate_content.return_value = json.dumps(
            [{"id": "s0", "score": 0.9, "rationale": "ok", "topics": []}]
        )

        processor = _make_processor(mock_client)
        stories = [
            _make_story(story_id="s0"),
            _make_story(story_id="s1"),
        ]
        result = processor.evaluate_stories(stories)

        assert result.scores["s0"] == pytest.approx(0.9)
        assert result.scores["s1"] == pytest.approx(0.5)
