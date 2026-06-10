"""Unit tests for Story ID generation."""

from datetime import UTC, datetime

import pytest

from src.features.store.models import DateConfidence, Item
from src.linker.story_id import (
    ExtractedStableIds,
    extract_all_stable_ids,
    extract_arxiv_id,
    extract_github_release_id,
    extract_hf_model_id,
    extract_modelscope_id,
    extract_stable_id,
    generate_story_id,
    get_date_bucket,
    normalize_title,
)


class TestExtractArxivId:
    """Tests for extract_arxiv_id function."""

    def test_extract_new_format(self) -> None:
        """Test extracting new format arXiv ID."""
        url = "https://arxiv.org/abs/2401.12345"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_extract_new_format_with_version(self) -> None:
        """Test extracting arXiv ID with version suffix."""
        url = "https://arxiv.org/abs/2401.12345v2"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_extract_pdf_url(self) -> None:
        """Test extracting from PDF URL."""
        url = "https://arxiv.org/pdf/2401.12345.pdf"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_extract_old_format(self) -> None:
        """Test extracting old format arXiv ID."""
        url = "https://arxiv.org/abs/cs.AI/0401234"
        assert extract_arxiv_id(url) == "cs.AI/0401234"

    def test_no_arxiv_id(self) -> None:
        """Test URL without arXiv ID."""
        url = "https://example.com/paper"
        assert extract_arxiv_id(url) is None

    def test_raw_arxiv_id(self) -> None:
        """Test raw arXiv ID string."""
        assert extract_arxiv_id("arxiv:2401.12345") == "2401.12345"


class TestExtractHfModelId:
    """Tests for extract_hf_model_id function."""

    def test_extract_model_id(self) -> None:
        """Test extracting HF model ID."""
        url = "https://huggingface.co/meta-llama/Llama-2-7b"
        assert extract_hf_model_id(url) == "meta-llama/llama-2-7b"

    def test_extract_model_id_with_path(self) -> None:
        """Test extracting model ID from model page with path."""
        url = "https://huggingface.co/mistralai/Mixtral-8x7B-v0.1/tree/main"
        result = extract_hf_model_id(url)
        assert result is not None
        assert result.startswith("mistralai/mixtral")

    def test_no_model_id(self) -> None:
        """Test URL without model ID."""
        url = "https://example.com/model"
        assert extract_hf_model_id(url) is None


class TestExtractGithubReleaseId:
    """Tests for extract_github_release_id function."""

    def test_extract_release_id(self) -> None:
        """Test extracting GitHub release ID."""
        url = "https://github.com/openai/whisper/releases/tag/v20231117"
        assert extract_github_release_id(url) == "openai/whisper:v20231117"

    def test_extract_release_without_tag(self) -> None:
        """Test extracting release with 'releases/' prefix."""
        url = "https://github.com/meta-llama/llama/releases/v1.0.0"
        assert extract_github_release_id(url) == "meta-llama/llama:v1.0.0"

    def test_no_release_id(self) -> None:
        """Test URL without release ID."""
        url = "https://github.com/openai/whisper"
        assert extract_github_release_id(url) is None


class TestExtractModelScopeId:
    """Tests for extract_modelscope_id function."""

    def test_extract_model_id(self) -> None:
        """Test extracting ModelScope model ID."""
        url = "https://modelscope.cn/models/qwen/Qwen2-7B"
        assert extract_modelscope_id(url) == "qwen/qwen2-7b"

    def test_no_model_id(self) -> None:
        """Test URL without model ID."""
        url = "https://modelscope.cn/home"
        assert extract_modelscope_id(url) is None


class TestNormalizeTitle:
    """Tests for normalize_title function."""

    def test_basic_normalization(self) -> None:
        """Test basic title normalization."""
        title = "GPT-4 Technical Report"
        assert normalize_title(title) == "gpt-4 technical report"

    def test_strip_special_chars(self) -> None:
        """Test stripping special characters."""
        title = "Model: GPT-4 (V2.0)!"
        normalized = normalize_title(title)
        assert "!" not in normalized
        assert "(" not in normalized
        assert ")" not in normalized

    def test_collapse_whitespace(self) -> None:
        """Test collapsing whitespace."""
        title = "GPT-4   Technical   Report"
        assert normalize_title(title) == "gpt-4 technical report"

    def test_unicode_normalization(self) -> None:
        """Test unicode normalization (NFKD decomposition)."""
        title = "Cafe\u0301"  # e with combining acute accent
        normalized = normalize_title(title)
        # NFKD normalizes - the accented char gets decomposed
        assert "caf" in normalized  # Contains the base
        assert normalized.startswith("caf")
        assert len(normalized) == 5  # 'c', 'a', 'f', 'e', accent (or composed)


class TestGetDateBucket:
    """Tests for get_date_bucket function."""

    def test_valid_date(self) -> None:
        """Test date bucket for valid date."""
        dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)
        assert get_date_bucket(dt) == "2024-01-15"

    def test_none_date(self) -> None:
        """Test date bucket for None."""
        assert get_date_bucket(None) == "unknown"


class TestExtractStableId:
    """Tests for extract_stable_id function."""

    def test_arxiv_priority(self) -> None:
        """Test arXiv ID is prioritized."""
        item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv-cs-ai",
            tier=1,
            kind="paper",
            title="Test Paper",
            content_hash="abc123",
            raw_json="{}",
        )
        stable_id, id_type = extract_stable_id(item)
        assert stable_id == "arxiv:2401.12345"
        assert id_type == "arxiv"

    def test_github_fallback(self) -> None:
        """Test GitHub release as fallback."""
        item = Item(
            url="https://github.com/org/repo/releases/tag/v1.0",
            source_id="github-releases",
            tier=0,
            kind="release",
            title="v1.0 Release",
            content_hash="abc123",
            raw_json="{}",
        )
        stable_id, id_type = extract_stable_id(item)
        assert stable_id == "github:org/repo:v1.0"
        assert id_type == "github"

    def test_hf_fallback(self) -> None:
        """Test HF model ID as fallback."""
        item = Item(
            url="https://huggingface.co/meta-llama/Llama-2-7b",
            source_id="hf-meta-llama",
            tier=0,
            kind="model",
            title="Llama 2 7B",
            content_hash="abc123",
            raw_json="{}",
        )
        stable_id, id_type = extract_stable_id(item)
        assert stable_id == "hf:meta-llama/llama-2-7b"
        assert id_type == "huggingface"

    def test_no_stable_id(self) -> None:
        """Test item with no stable ID."""
        item = Item(
            url="https://example.com/blog/post",
            source_id="example-blog",
            tier=1,
            kind="blog",
            title="Example Post",
            content_hash="abc123",
            raw_json="{}",
        )
        stable_id, id_type = extract_stable_id(item)
        assert stable_id is None
        assert id_type == "none"


class TestGenerateStoryId:
    """Tests for generate_story_id function."""

    def test_empty_items_raises(self) -> None:
        """Test that empty items raises ValueError."""
        with pytest.raises(ValueError, match="empty item list"):
            generate_story_id([])

    def test_stable_id_used(self) -> None:
        """Test that stable ID is used when available."""
        item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv",
            tier=1,
            kind="paper",
            title="Paper",
            content_hash="abc",
            raw_json="{}",
        )
        story_id, id_type = generate_story_id([item])
        assert story_id == "arxiv:2401.12345"
        assert id_type == "arxiv"

    def test_fallback_deterministic(self) -> None:
        """Test fallback story_id is deterministic."""
        item = Item(
            url="https://example.com/post1",
            source_id="blog",
            tier=1,
            kind="blog",
            title="Test Blog Post",
            published_at=datetime(2024, 1, 15, tzinfo=UTC),
            date_confidence=DateConfidence.HIGH,
            content_hash="abc",
            raw_json="{}",
        )

        id1, type1 = generate_story_id([item], ["openai"])
        id2, type2 = generate_story_id([item], ["openai"])

        assert id1 == id2
        assert type1 == type2 == "fallback"

    def test_fallback_differs_with_entity(self) -> None:
        """Test fallback differs with different entity."""
        item = Item(
            url="https://example.com/post1",
            source_id="blog",
            tier=1,
            kind="blog",
            title="Test Blog Post",
            content_hash="abc",
            raw_json="{}",
        )

        id1, _ = generate_story_id([item], ["openai"])
        id2, _ = generate_story_id([item], ["anthropic"])

        assert id1 != id2


class TestExtractAllStableIds:
    """Tests for extract_all_stable_ids function."""

    def test_empty_items_returns_empty_ids(self) -> None:
        """Test that empty items list returns empty IDs."""
        result = extract_all_stable_ids([])
        assert result.arxiv_id is None
        assert result.hf_model_id is None
        assert result.github_release_url is None
        assert result.modelscope_id is None

    def test_extracts_arxiv_id(self) -> None:
        """Test extraction of arXiv ID."""
        item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv-rss",
            tier=1,
            kind="paper",
            title="Test Paper",
            content_hash="abc123",
            raw_json="{}",
        )
        result = extract_all_stable_ids([item])
        assert result.arxiv_id == "2401.12345"
        assert result.hf_model_id is None
        assert result.github_release_url is None

    def test_extracts_multiple_id_types(self) -> None:
        """Test extraction of multiple ID types from different items."""
        arxiv_item = Item(
            url="https://arxiv.org/abs/2401.12345",
            source_id="arxiv",
            tier=1,
            kind="paper",
            title="Paper",
            content_hash="abc",
            raw_json="{}",
        )
        hf_item = Item(
            url="https://huggingface.co/meta-llama/Llama-2-7b",
            source_id="hf",
            tier=1,
            kind="model",
            title="Llama 2",
            content_hash="def",
            raw_json="{}",
        )
        result = extract_all_stable_ids([arxiv_item, hf_item])
        assert result.arxiv_id == "2401.12345"
        assert result.hf_model_id == "meta-llama/llama-2-7b"

    def test_extracts_github_release_url(self) -> None:
        """Test extraction of GitHub release URL."""
        item = Item(
            url="https://github.com/openai/whisper/releases/tag/v20231117",
            source_id="gh-releases",
            tier=1,
            kind="release",
            title="Whisper Release",
            content_hash="abc",
            raw_json="{}",
        )
        result = extract_all_stable_ids([item])
        assert (
            result.github_release_url
            == "https://github.com/openai/whisper/releases/tag/v20231117"
        )

    def test_to_dict_excludes_none_values(self) -> None:
        """Test that to_dict only includes non-None values."""
        ids = ExtractedStableIds(arxiv_id="2401.12345")
        result = ids.to_dict()
        assert result == {"arxiv_id": "2401.12345"}
        assert "hf_model_id" not in result
        assert "github_release_url" not in result

    def test_to_dict_includes_all_present_values(self) -> None:
        """Test that to_dict includes all non-None values."""
        ids = ExtractedStableIds(
            arxiv_id="2401.12345",
            hf_model_id="meta-llama/llama-2-7b",
            github_release_url="https://github.com/openai/whisper/releases/tag/v1",
        )
        result = ids.to_dict()
        assert len(result) == 3
        assert result["arxiv_id"] == "2401.12345"
        assert result["hf_model_id"] == "meta-llama/llama-2-7b"


class TestEdgeCases:
    """Edge case tests for story ID generation."""

    def test_malformed_url_no_crash(self) -> None:
        """Test that malformed URLs don't crash extraction."""
        item = Item(
            url="not-a-valid-url",
            source_id="test",
            tier=1,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )
        result = extract_all_stable_ids([item])
        assert result.arxiv_id is None
        assert result.hf_model_id is None

    def test_special_characters_in_title(self) -> None:
        """Test normalization handles special characters."""
        title = 'Test: A Paper with "Quotes" & <Special> Characters!'
        normalized = normalize_title(title)
        assert '"' not in normalized
        assert "<" not in normalized
        assert ">" not in normalized

    def test_empty_title_normalization(self) -> None:
        """Test normalization of empty title."""
        assert normalize_title("") == ""
        assert normalize_title("   ") == ""

    def test_very_long_title_truncation(self) -> None:
        """Test that very long titles are truncated."""
        long_title = "A" * 500
        normalized = normalize_title(long_title)
        assert len(normalized) <= 128  # MAX_TITLE_LENGTH

    def test_malformed_raw_json_no_crash(self) -> None:
        """Test that malformed raw_json doesn't crash extraction."""
        item = Item(
            url="https://example.com/paper",
            source_id="test",
            tier=1,
            kind="paper",
            title="Test",
            content_hash="abc",
            raw_json="not-valid-json",
        )
        stable_id, id_type = extract_stable_id(item)
        assert stable_id is None
        assert id_type == "none"
