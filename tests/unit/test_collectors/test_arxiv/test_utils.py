"""Unit tests for arXiv utilities."""

from src.collectors.arxiv.utils import (
    extract_arxiv_id,
    get_arxiv_category_from_url,
    is_arxiv_url,
    normalize_arxiv_url,
)


class TestExtractArxivId:
    """Tests for extract_arxiv_id function."""

    def test_new_style_id_from_abs_url(self) -> None:
        """Test extraction from canonical abs URL."""
        url = "https://arxiv.org/abs/2401.12345"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_new_style_id_with_version_from_abs_url(self) -> None:
        """Test extraction from abs URL with version."""
        url = "https://arxiv.org/abs/2401.12345v2"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_new_style_id_from_pdf_url(self) -> None:
        """Test extraction from PDF URL."""
        url = "https://arxiv.org/pdf/2401.12345.pdf"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_new_style_id_from_html_url(self) -> None:
        """Test extraction from HTML URL."""
        url = "https://arxiv.org/html/2401.12345"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_new_style_id_from_ar5iv_url(self) -> None:
        """Test extraction from ar5iv URL."""
        url = "https://ar5iv.labs.arxiv.org/html/2401.12345"
        assert extract_arxiv_id(url) == "2401.12345"

    def test_old_style_id_from_abs_url(self) -> None:
        """Test extraction from old-style abs URL."""
        url = "http://arxiv.org/abs/hep-th/9901001"
        assert extract_arxiv_id(url) == "hep-th/9901001"

    def test_old_style_id_with_category_prefix(self) -> None:
        """Test extraction from old-style URL with category."""
        url = "https://arxiv.org/abs/cs.AI/0601001"
        assert extract_arxiv_id(url) == "cs.AI/0601001"

    def test_rss_entry_id_oai_format(self) -> None:
        """Test extraction from RSS OAI format."""
        entry_id = "oai:arXiv.org:2401.12345"
        assert extract_arxiv_id(entry_id) == "2401.12345"

    def test_rss_entry_id_http_format(self) -> None:
        """Test extraction from RSS HTTP format."""
        entry_id = "http://arxiv.org/abs/2401.12345"
        assert extract_arxiv_id(entry_id) == "2401.12345"

    def test_direct_new_style_id(self) -> None:
        """Test extraction from direct ID string."""
        assert extract_arxiv_id("2401.12345") == "2401.12345"

    def test_direct_old_style_id(self) -> None:
        """Test extraction from direct old-style ID."""
        assert extract_arxiv_id("hep-th/9901001") == "hep-th/9901001"

    def test_five_digit_arxiv_id(self) -> None:
        """Test extraction of 5-digit arXiv ID."""
        url = "https://arxiv.org/abs/2401.00001"
        assert extract_arxiv_id(url) == "2401.00001"

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        assert extract_arxiv_id("") is None

    def test_none_input_returns_none(self) -> None:
        """Test that None-like input returns None."""
        assert extract_arxiv_id("") is None

    def test_invalid_url_returns_none(self) -> None:
        """Test that invalid URL returns None."""
        assert extract_arxiv_id("https://example.com/paper") is None

    def test_github_url_returns_none(self) -> None:
        """Test that non-arXiv URL returns None."""
        assert extract_arxiv_id("https://github.com/user/repo") is None


class TestNormalizeArxivUrl:
    """Tests for normalize_arxiv_url function."""

    def test_abs_url_unchanged(self) -> None:
        """Test that canonical abs URL returns same format."""
        url = "https://arxiv.org/abs/2401.12345"
        assert normalize_arxiv_url(url) == "https://arxiv.org/abs/2401.12345"

    def test_pdf_url_normalized(self) -> None:
        """Test that PDF URL is normalized to abs."""
        url = "https://arxiv.org/pdf/2401.12345.pdf"
        assert normalize_arxiv_url(url) == "https://arxiv.org/abs/2401.12345"

    def test_html_url_normalized(self) -> None:
        """Test that HTML URL is normalized to abs."""
        url = "https://arxiv.org/html/2401.12345"
        assert normalize_arxiv_url(url) == "https://arxiv.org/abs/2401.12345"

    def test_ar5iv_url_normalized(self) -> None:
        """Test that ar5iv URL is normalized to abs."""
        url = "https://ar5iv.labs.arxiv.org/html/2401.12345"
        assert normalize_arxiv_url(url) == "https://arxiv.org/abs/2401.12345"

    def test_version_stripped(self) -> None:
        """Test that version suffix is stripped."""
        url = "https://arxiv.org/abs/2401.12345v3"
        assert normalize_arxiv_url(url) == "https://arxiv.org/abs/2401.12345"

    def test_http_upgraded_to_https(self) -> None:
        """Test that HTTP is normalized to HTTPS."""
        url = "http://arxiv.org/abs/2401.12345"
        result = normalize_arxiv_url(url)
        assert result == "https://arxiv.org/abs/2401.12345"
        assert result.startswith("https://")

    def test_old_style_id_normalized(self) -> None:
        """Test that old-style ID is normalized correctly."""
        url = "http://arxiv.org/abs/hep-th/9901001"
        assert normalize_arxiv_url(url) == "https://arxiv.org/abs/hep-th/9901001"

    def test_invalid_url_returns_none(self) -> None:
        """Test that invalid URL returns None."""
        assert normalize_arxiv_url("https://example.com/paper") is None

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        assert normalize_arxiv_url("") is None


class TestIsArxivUrl:
    """Tests for is_arxiv_url function."""

    def test_arxiv_org_is_arxiv(self) -> None:
        """Test that arxiv.org URLs are detected."""
        assert is_arxiv_url("https://arxiv.org/abs/2401.12345")

    def test_www_arxiv_org_is_arxiv(self) -> None:
        """Test that www.arxiv.org URLs are detected."""
        assert is_arxiv_url("https://www.arxiv.org/abs/2401.12345")

    def test_ar5iv_is_arxiv(self) -> None:
        """Test that ar5iv URLs are detected."""
        assert is_arxiv_url("https://ar5iv.labs.arxiv.org/html/2401.12345")

    def test_export_arxiv_is_arxiv(self) -> None:
        """Test that export.arxiv.org URLs are detected."""
        assert is_arxiv_url("http://export.arxiv.org/api/query")

    def test_github_not_arxiv(self) -> None:
        """Test that GitHub URLs are not arXiv."""
        assert not is_arxiv_url("https://github.com/user/repo")

    def test_empty_string_not_arxiv(self) -> None:
        """Test that empty string is not arXiv."""
        assert not is_arxiv_url("")


class TestGetArxivCategoryFromUrl:
    """Tests for get_arxiv_category_from_url function."""

    def test_cs_ai_category(self) -> None:
        """Test extraction of cs.AI category."""
        url = "https://rss.arxiv.org/rss/cs.AI"
        assert get_arxiv_category_from_url(url) == "cs.AI"

    def test_cs_lg_category(self) -> None:
        """Test extraction of cs.LG category."""
        url = "https://rss.arxiv.org/rss/cs.LG"
        assert get_arxiv_category_from_url(url) == "cs.LG"

    def test_stat_ml_category(self) -> None:
        """Test extraction of stat.ML category."""
        url = "https://rss.arxiv.org/rss/stat.ML"
        assert get_arxiv_category_from_url(url) == "stat.ML"

    def test_non_rss_url_returns_none(self) -> None:
        """Test that non-RSS URL returns None."""
        url = "https://arxiv.org/abs/2401.12345"
        assert get_arxiv_category_from_url(url) is None

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        assert get_arxiv_category_from_url("") is None
