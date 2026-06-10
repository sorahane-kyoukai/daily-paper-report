"""Unit tests for URL canonicalization."""

from src.features.store.url import (
    DEFAULT_STRIP_PARAMS,
    canonicalize_url,
)


class TestCanonicalizeUrl:
    """Tests for canonicalize_url function."""

    def test_empty_url(self) -> None:
        """Test empty URL returns empty."""
        assert canonicalize_url("") == ""

    def test_strips_utm_params(self) -> None:
        """Test UTM parameters are stripped."""
        url = "https://example.com/article?utm_source=twitter&utm_medium=social"
        result = canonicalize_url(url)
        assert result == "https://example.com/article"

    def test_strips_multiple_tracking_params(self) -> None:
        """Test multiple tracking parameters are stripped."""
        url = "https://example.com/article?utm_source=x&fbclid=abc&gclid=def"
        result = canonicalize_url(url)
        assert result == "https://example.com/article"

    def test_preserves_other_params(self) -> None:
        """Test non-tracking parameters are preserved."""
        url = "https://example.com/search?q=test&page=2&utm_source=google"
        result = canonicalize_url(url)
        assert "q=test" in result
        assert "page=2" in result
        assert "utm_source" not in result

    def test_removes_fragments(self) -> None:
        """Test fragments are removed by default."""
        url = "https://example.com/article#section-1"
        result = canonicalize_url(url)
        assert result == "https://example.com/article"

    def test_preserves_fragments_when_requested(self) -> None:
        """Test fragments can be preserved."""
        url = "https://example.com/article#section-1"
        result = canonicalize_url(url, preserve_fragments=True)
        assert result == "https://example.com/article#section-1"

    def test_removes_trailing_slash(self) -> None:
        """Test trailing slashes are removed."""
        url = "https://example.com/article/"
        result = canonicalize_url(url)
        assert result == "https://example.com/article"

    def test_preserves_root_slash(self) -> None:
        """Test root path slash is preserved."""
        url = "https://example.com/"
        result = canonicalize_url(url)
        assert result == "https://example.com/"

    def test_lowercase_scheme_and_host(self) -> None:
        """Test scheme and host are lowercased."""
        url = "HTTPS://EXAMPLE.COM/Article"
        result = canonicalize_url(url)
        assert result.startswith("https://example.com/")
        # Path case should be preserved
        assert "Article" in result

    def test_custom_strip_params(self) -> None:
        """Test custom strip parameters."""
        url = "https://example.com/article?custom_param=value&keep=yes"
        result = canonicalize_url(url, strip_params=["custom_param"])
        assert "keep=yes" in result
        assert "custom_param" not in result

    def test_upgrades_http_to_https_for_known_sites(self) -> None:
        """Test HTTP is upgraded to HTTPS for known sites."""
        url = "http://arxiv.org/abs/2301.00001"
        result = canonicalize_url(url)
        assert result.startswith("https://")

    def test_keeps_http_for_unknown_sites(self) -> None:
        """Test HTTP is kept for unknown sites."""
        url = "http://unknown-site.com/article"
        result = canonicalize_url(url)
        assert result.startswith("http://")


class TestArxivUrlNormalization:
    """Tests for arXiv URL normalization."""

    def test_pdf_to_abs(self) -> None:
        """Test PDF URL converted to abs."""
        url = "https://arxiv.org/pdf/2301.00001.pdf"
        result = canonicalize_url(url)
        assert result == "https://arxiv.org/abs/2301.00001"

    def test_pdf_without_extension(self) -> None:
        """Test PDF URL without .pdf extension."""
        url = "https://arxiv.org/pdf/2301.00001"
        result = canonicalize_url(url)
        assert result == "https://arxiv.org/abs/2301.00001"

    def test_ar5iv_to_abs(self) -> None:
        """Test ar5iv HTML URL converted to abs."""
        url = "https://ar5iv.labs.arxiv.org/html/2301.00001"
        result = canonicalize_url(url)
        assert result == "https://arxiv.org/abs/2301.00001"

    def test_http_abs_upgraded(self) -> None:
        """Test HTTP abs URL upgraded to HTTPS."""
        url = "http://arxiv.org/abs/2301.00001"
        result = canonicalize_url(url)
        assert result == "https://arxiv.org/abs/2301.00001"

    def test_versioned_arxiv_id(self) -> None:
        """Test versioned arXiv IDs are preserved."""
        url = "https://arxiv.org/abs/2301.00001v2"
        result = canonicalize_url(url)
        assert result == "https://arxiv.org/abs/2301.00001v2"

    def test_old_style_arxiv_id(self) -> None:
        """Test old-style arXiv IDs (hep-ph/1234567)."""
        url = "https://arxiv.org/abs/hep-ph/0001234"
        result = canonicalize_url(url)
        assert result == "https://arxiv.org/abs/hep-ph/0001234"


class TestDefaultStripParams:
    """Tests for DEFAULT_STRIP_PARAMS constant."""

    def test_contains_utm_params(self) -> None:
        """Test default params include UTM parameters."""
        assert "utm_source" in DEFAULT_STRIP_PARAMS
        assert "utm_medium" in DEFAULT_STRIP_PARAMS
        assert "utm_campaign" in DEFAULT_STRIP_PARAMS

    def test_contains_social_params(self) -> None:
        """Test default params include social tracking."""
        assert "fbclid" in DEFAULT_STRIP_PARAMS
        assert "gclid" in DEFAULT_STRIP_PARAMS

    def test_strip_is_case_insensitive(self) -> None:
        """Test parameter stripping is case-insensitive."""
        url = "https://example.com/article?UTM_SOURCE=twitter&UTM_MEDIUM=social"
        result = canonicalize_url(url)
        assert result == "https://example.com/article"
