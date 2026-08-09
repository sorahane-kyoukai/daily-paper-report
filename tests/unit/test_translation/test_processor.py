"""Tests for the TranslationProcessor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.features.llm.errors import LlmApiError
from src.features.translation.models import (
    CURRENT_TRANSLATION_PROMPT_VERSION,
)
from src.features.translation.processor import TranslationProcessor, _create_batches


def _make_story(story_id: str, title: str, summary: str = "") -> dict[str, object]:
    return {"story_id": story_id, "title": title, "summary": summary}


def _make_llm_response(entries: list[dict[str, str]]) -> str:
    return json.dumps(entries)


class TestCreateBatches:
    """Tests for batch splitting."""

    def test_empty_input(self) -> None:
        assert _create_batches([], 5) == []

    def test_single_batch(self) -> None:
        items: list[dict[str, object]] = [{"id": i} for i in range(3)]
        batches = _create_batches(items, 5)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_exact_batch_size(self) -> None:
        items: list[dict[str, object]] = [{"id": i} for i in range(5)]
        batches = _create_batches(items, 5)
        assert len(batches) == 1

    def test_multiple_batches(self) -> None:
        items: list[dict[str, object]] = [{"id": i} for i in range(12)]
        batches = _create_batches(items, 5)
        assert len(batches) == 3
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5
        assert len(batches[2]) == 2


class TestTranslationProcessor:
    """Tests for TranslationProcessor."""

    def _make_processor(
        self, tmp_path: Path, responses: list[str] | None = None
    ) -> tuple[TranslationProcessor, MagicMock]:
        client = MagicMock()
        if responses:
            client.generate_content.side_effect = responses
        processor = TranslationProcessor(client=client, output_dir=tmp_path)
        return processor, client

    def test_translate_single_story(self, tmp_path: Path) -> None:
        response = _make_llm_response(
            [
                {
                    "id": "s1",
                    "title_zh": "\u6e2c\u8a66\u6a19\u984c",
                    "summary_zh": "\u6e2c\u8a66\u6458\u8981",
                }
            ]
        )
        processor, client = self._make_processor(tmp_path, [response])

        stories = [_make_story("s1", "Test Title", "Test Summary")]
        result = processor.translate(stories)

        assert "s1" in result
        assert result["s1"].title_zh == "\u6e2c\u8a66\u6a19\u984c"
        assert result["s1"].summary_zh == "\u6e2c\u8a66\u6458\u8981"
        client.generate_content.assert_called_once()

    def test_skip_cached_stories(self, tmp_path: Path) -> None:
        # Pre-populate cache
        cache_dir = tmp_path / "api"
        cache_dir.mkdir(parents=True)
        cache_path = cache_dir / "translations_zh.json"
        cache_data = {
            "s1": {
                "story_id": "s1",
                "title_zh": "\u5df2\u7de9\u5b58",
                "summary_zh": "\u6458\u8981",
                "prompt_version": CURRENT_TRANSLATION_PROMPT_VERSION,
                "model": "deepseek-v4-flash",
                "fulltext_sha256": "",
            }
        }
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False))

        processor, client = self._make_processor(tmp_path)
        stories = [_make_story("s1", "Test Title")]
        result = processor.translate(stories)

        assert "s1" in result
        assert result["s1"].title_zh == "\u5df2\u7de9\u5b58"
        client.generate_content.assert_not_called()

    def test_stale_cached_story_is_retranslated(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "api"
        cache_dir.mkdir(parents=True)
        cache_path = cache_dir / "translations_zh.json"
        cache_data = {
            "s1": {
                "story_id": "s1",
                "title_zh": "\u820a\u7de9\u5b58",
                "summary_zh": "\u77ed\u6458\u8981",
            }
        }
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False))

        response = _make_llm_response(
            [
                {
                    "id": "s1",
                    "title_zh": "\u65b0\u7ffb\u8b6f",
                    "summary_zh": "\u8f03\u9577\u6458\u8981",
                }
            ]
        )
        processor, client = self._make_processor(tmp_path, [response])

        result = processor.translate([_make_story("s1", "Test Title")])

        assert result["s1"].title_zh == "\u65b0\u7ffb\u8b6f"
        assert result["s1"].prompt_version == CURRENT_TRANSLATION_PROMPT_VERSION
        client.generate_content.assert_called_once()

    def test_mixed_cached_and_new(self, tmp_path: Path) -> None:
        # Pre-populate cache for s1
        cache_dir = tmp_path / "api"
        cache_dir.mkdir(parents=True)
        cache_path = cache_dir / "translations_zh.json"
        cache_data = {
            "s1": {
                "story_id": "s1",
                "title_zh": "\u5df2\u7de9\u5b58",
                "summary_zh": "",
                "prompt_version": CURRENT_TRANSLATION_PROMPT_VERSION,
                "model": "deepseek-v4-flash",
                "fulltext_sha256": "",
            }
        }
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False))

        response = _make_llm_response(
            [{"id": "s2", "title_zh": "\u65b0\u7ffb\u8b6f", "summary_zh": ""}]
        )
        processor, client = self._make_processor(tmp_path, [response])

        stories = [
            _make_story("s1", "Cached Story"),
            _make_story("s2", "New Story"),
        ]
        result = processor.translate(stories)

        assert "s1" in result
        assert "s2" in result
        assert result["s1"].title_zh == "\u5df2\u7de9\u5b58"
        assert result["s2"].title_zh == "\u65b0\u7ffb\u8b6f"
        client.generate_content.assert_called_once()

    def test_api_error_skips_batch(self, tmp_path: Path) -> None:
        processor, client = self._make_processor(tmp_path)
        client.generate_content.side_effect = LlmApiError("Rate limited")

        stories = [_make_story("s1", "Title")]
        result = processor.translate(stories)

        # Should return empty (no cached, no successful translations)
        assert "s1" not in result

    def test_api_error_isolated_per_paper(self, tmp_path: Path) -> None:
        responses: list[object] = [
            LlmApiError("Empty content"),
            LlmApiError("Empty content"),
            LlmApiError("Empty content"),
            _make_llm_response(
                [{"id": "s1", "title_zh": "\u7ffb\u8b6f1", "summary_zh": ""}]
            ),
            _make_llm_response(
                [{"id": "s2", "title_zh": "\u7ffb\u8b6f2", "summary_zh": ""}]
            ),
            _make_llm_response(
                [{"id": "s3", "title_zh": "\u7ffb\u8b6f3", "summary_zh": ""}]
            ),
        ]
        processor, client = self._make_processor(tmp_path)
        client.generate_content.side_effect = responses

        stories = [_make_story(f"s{i}", f"Title {i}") for i in range(4)]
        result = processor.translate(stories)

        assert len(result) == 3
        assert client.generate_content.call_count == 6

    def test_parse_error_skips_batch(self, tmp_path: Path) -> None:
        processor, client = self._make_processor(tmp_path, ["not json at all"] * 3)

        stories = [_make_story("s1", "Title")]
        result = processor.translate(stories)

        assert "s1" not in result
        assert client.generate_content.call_count == 3

    def test_invalid_story_id_ignored(self, tmp_path: Path) -> None:
        response = _make_llm_response(
            [
                {"id": "s1", "title_zh": "\u6b63\u78ba", "summary_zh": ""},
                {"id": "unknown", "title_zh": "\u7121\u6548", "summary_zh": ""},
            ]
        )
        processor, client = self._make_processor(tmp_path, [response])

        stories = [_make_story("s1", "Title")]
        result = processor.translate(stories)

        assert "s1" in result
        assert "unknown" not in result

    def test_numeric_ids_map_to_batch_order(self, tmp_path: Path) -> None:
        responses = [
            _make_llm_response(
                [{"id": "1", "title_zh": "\u7b2c\u4e00", "summary_zh": ""}]
            ),
            _make_llm_response(
                [{"id": "1", "title_zh": "\u7b2c\u4e8c", "summary_zh": ""}]
            ),
        ]
        processor, _client = self._make_processor(tmp_path, responses)

        stories = [
            _make_story("story-a", "First"),
            _make_story("story-b", "Second"),
        ]
        result = processor.translate(stories)

        assert result["story-a"].title_zh == "\u7b2c\u4e00"
        assert result["story-b"].title_zh == "\u7b2c\u4e8c"

    def test_bracketed_ids_map_to_story_ids(self, tmp_path: Path) -> None:
        response = _make_llm_response(
            [{"id": "[story-a]", "title_zh": "\u7ffb\u8b6f", "summary_zh": ""}]
        )
        processor, _client = self._make_processor(tmp_path, [response])

        stories = [_make_story("story-a", "First")]
        result = processor.translate(stories)

        assert result["story-a"].title_zh == "\u7ffb\u8b6f"

    def test_namespace_prefix_omission_maps_to_story_id(self, tmp_path: Path) -> None:
        response = _make_llm_response(
            [{"id": "abc123", "title_zh": "\u7ffb\u8b6f", "summary_zh": ""}]
        )
        processor, client = self._make_processor(tmp_path, [response])

        result = processor.translate([_make_story("fallback:abc123", "First")])

        assert result["fallback:abc123"].title_zh == "\u7ffb\u8b6f"
        assert client.generate_content.call_count == 1

    def test_missing_title_zh_skipped(self, tmp_path: Path) -> None:
        response = _make_llm_response(
            [{"id": "s1", "title_zh": "", "summary_zh": "\u6458\u8981"}]
        )
        processor, client = self._make_processor(tmp_path, [response] * 3)

        stories = [_make_story("s1", "Title")]
        result = processor.translate(stories)

        assert "s1" not in result
        assert client.generate_content.call_count == 3

    def test_markdown_fenced_response(self, tmp_path: Path) -> None:
        inner = json.dumps([{"id": "s1", "title_zh": "\u6e2c\u8a66", "summary_zh": ""}])
        response = f"```json\n{inner}\n```"
        processor, client = self._make_processor(tmp_path, [response])

        stories = [_make_story("s1", "Title")]
        result = processor.translate(stories)

        assert "s1" in result
        assert result["s1"].title_zh == "\u6e2c\u8a66"

    def test_cache_persisted_after_translate(self, tmp_path: Path) -> None:
        response = _make_llm_response(
            [{"id": "s1", "title_zh": "\u6e2c\u8a66", "summary_zh": ""}]
        )
        processor, _ = self._make_processor(tmp_path, [response])

        stories = [_make_story("s1", "Title")]
        processor.translate(stories)

        cache_path = tmp_path / "api" / "translations_zh.json"
        assert cache_path.exists()
        data = json.loads(cache_path.read_text())
        assert "s1" in data

    def test_multiple_batches(self, tmp_path: Path) -> None:
        # Full-paper guides use one request per story.
        responses = [
            _make_llm_response(
                [{"id": f"s{i}", "title_zh": f"\u7ffb\u8b6f{i}", "summary_zh": ""}]
            )
            for i in range(7)
        ]
        processor, client = self._make_processor(tmp_path, responses)

        stories = [_make_story(f"s{i}", f"Title {i}") for i in range(7)]
        result = processor.translate(stories)

        assert len(result) == 7
        assert client.generate_content.call_count == 7
