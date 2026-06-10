"""Tests for platform collector helper functions."""

from unittest.mock import MagicMock, patch

from src.collectors.platform.helpers import (
    build_pdf_url,
    extract_nested_value,
    get_auth_token,
    is_auth_error,
    truncate_text,
)
from src.features.fetch.models import FetchErrorClass


class TestIsAuthError:
    """Tests for is_auth_error helper."""

    def test_no_error_returns_false(self) -> None:
        """Test that no error returns False."""
        result = MagicMock()
        result.error = None
        assert is_auth_error(result) is False

    def test_401_returns_true(self) -> None:
        """Test that 401 status code returns True."""
        result = MagicMock()
        result.error = MagicMock()
        result.status_code = 401
        result.error.error_class = FetchErrorClass.HTTP_4XX
        assert is_auth_error(result) is True

    def test_403_returns_true(self) -> None:
        """Test that 403 status code returns True."""
        result = MagicMock()
        result.error = MagicMock()
        result.status_code = 403
        result.error.error_class = FetchErrorClass.HTTP_4XX
        assert is_auth_error(result) is True

    def test_404_returns_false(self) -> None:
        """Test that 404 status code returns False."""
        result = MagicMock()
        result.error = MagicMock()
        result.status_code = 404
        result.error.error_class = FetchErrorClass.HTTP_4XX
        assert is_auth_error(result) is False

    def test_500_returns_false(self) -> None:
        """Test that 500 status code returns False."""
        result = MagicMock()
        result.error = MagicMock()
        result.status_code = 500
        result.error.error_class = FetchErrorClass.HTTP_5XX
        assert is_auth_error(result) is False


class TestGetAuthToken:
    """Tests for get_auth_token helper."""

    def test_github_token(self) -> None:
        """Test getting GitHub token from environment."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test_token"}):
            assert get_auth_token("github") == "test_token"

    def test_hf_token(self) -> None:
        """Test getting HuggingFace token from environment."""
        with patch.dict("os.environ", {"HF_TOKEN": "hf_test"}):
            assert get_auth_token("huggingface") == "hf_test"

    def test_openreview_token(self) -> None:
        """Test getting OpenReview token from environment."""
        with patch.dict("os.environ", {"OPENREVIEW_TOKEN": "or_test"}):
            assert get_auth_token("openreview") == "or_test"

    def test_missing_token_returns_none(self) -> None:
        """Test missing token returns None."""
        with patch.dict("os.environ", {}, clear=True):
            assert get_auth_token("github") is None

    def test_unknown_platform_returns_none(self) -> None:
        """Test unknown platform returns None."""
        assert get_auth_token("unknown_platform") is None


class TestExtractNestedValue:
    """Tests for extract_nested_value helper."""

    def test_direct_string(self) -> None:
        """Test extracting direct string value."""
        assert extract_nested_value("direct value") == "direct value"

    def test_nested_dict_with_value(self) -> None:
        """Test extracting nested dict with value key."""
        assert extract_nested_value({"value": "nested value"}) == "nested value"

    def test_nested_dict_without_value(self) -> None:
        """Test extracting nested dict without value key."""
        assert extract_nested_value({"other": "key"}) is None

    def test_none_value(self) -> None:
        """Test None input returns None."""
        assert extract_nested_value(None) is None


class TestBuildPdfUrl:
    """Tests for build_pdf_url helper."""

    def test_relative_pdf_path(self) -> None:
        """Test relative /pdf path."""
        result = build_pdf_url("/pdf/abc123", "abc123")
        assert result == "https://openreview.net/pdf/abc123"

    def test_full_http_url(self) -> None:
        """Test full HTTP URL passthrough."""
        result = build_pdf_url("https://example.com/paper.pdf", "abc123")
        assert result == "https://example.com/paper.pdf"

    def test_other_value_constructs_url(self) -> None:
        """Test other value constructs URL from forum_id."""
        result = build_pdf_url("some_path", "abc123")
        assert result == "https://openreview.net/pdf?id=abc123"

    def test_nested_pdf_field(self) -> None:
        """Test nested PDF field extraction."""
        result = build_pdf_url({"value": "/pdf/nested"}, "abc123")
        assert result == "https://openreview.net/pdf/nested"

    def test_none_returns_none(self) -> None:
        """Test None input returns None."""
        assert build_pdf_url(None, "abc123") is None

    def test_empty_string_returns_none(self) -> None:
        """Test empty string returns None."""
        assert build_pdf_url("", "abc123") is None


class TestTruncateText:
    """Tests for truncate_text helper."""

    def test_short_text_unchanged(self) -> None:
        """Test short text is unchanged."""
        assert truncate_text("short", 100) == "short"

    def test_exact_length_unchanged(self) -> None:
        """Test text at exact length is unchanged."""
        assert truncate_text("12345", 5) == "12345"

    def test_long_text_truncated(self) -> None:
        """Test long text is truncated."""
        assert truncate_text("1234567890", 5) == "12345"

    def test_empty_string(self) -> None:
        """Test empty string is unchanged."""
        assert truncate_text("", 10) == ""
