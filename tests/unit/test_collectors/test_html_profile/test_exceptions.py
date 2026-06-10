"""Tests for HTML profile exceptions."""

from src.collectors.html_profile.exceptions import (
    ContentTypeError,
    CrossDomainRedirectError,
    DateExtractionError,
    HtmlProfileError,
    ItemPageFetchError,
    ProfileNotFoundError,
)


class TestHtmlProfileError:
    """Tests for HtmlProfileError base class."""

    def test_message(self) -> None:
        """Test that message is set correctly."""
        error = HtmlProfileError("Test error")
        assert str(error) == "Test error"
        assert error.domain is None

    def test_with_domain(self) -> None:
        """Test that domain is set correctly."""
        error = HtmlProfileError("Test error", domain="example.com")
        assert error.domain == "example.com"

    def test_inheritance(self) -> None:
        """Test that it inherits from Exception."""
        error = HtmlProfileError("Test")
        assert isinstance(error, Exception)


class TestContentTypeError:
    """Tests for ContentTypeError."""

    def test_content_type_attribute(self) -> None:
        """Test that content_type is stored."""
        error = ContentTypeError(
            "Content type not allowed",
            content_type="image/png",
        )
        assert error.content_type == "image/png"
        assert "Content type not allowed" in str(error)

    def test_with_domain(self) -> None:
        """Test with domain specified."""
        error = ContentTypeError(
            "Error",
            content_type="application/pdf",
            domain="example.com",
        )
        assert error.domain == "example.com"

    def test_inheritance(self) -> None:
        """Test that it inherits from HtmlProfileError."""
        error = ContentTypeError("Test", content_type="image/png")
        assert isinstance(error, HtmlProfileError)


class TestCrossDomainRedirectError:
    """Tests for CrossDomainRedirectError."""

    def test_domains_stored(self) -> None:
        """Test that domains are stored."""
        error = CrossDomainRedirectError(
            "Redirect blocked",
            from_domain="example.com",
            to_domain="evil.com",
        )
        assert error.from_domain == "example.com"
        assert error.to_domain == "evil.com"
        assert error.domain == "example.com"

    def test_inheritance(self) -> None:
        """Test inheritance."""
        error = CrossDomainRedirectError(
            "Test",
            from_domain="a.com",
            to_domain="b.com",
        )
        assert isinstance(error, HtmlProfileError)


class TestDateExtractionError:
    """Tests for DateExtractionError."""

    def test_method_and_raw_date(self) -> None:
        """Test that method and raw_date are stored."""
        error = DateExtractionError(
            "Failed to parse date",
            method="time_element",
            raw_date="invalid-date",
        )
        assert error.method == "time_element"
        assert error.raw_date == "invalid-date"

    def test_optional_fields(self) -> None:
        """Test with optional fields."""
        error = DateExtractionError("Error")
        assert error.method is None
        assert error.raw_date is None
        assert error.domain is None


class TestProfileNotFoundError:
    """Tests for ProfileNotFoundError."""

    def test_url_stored(self) -> None:
        """Test that URL is stored."""
        error = ProfileNotFoundError(
            "Profile not found",
            url="https://example.com/page",
            domain="example.com",
        )
        assert error.url == "https://example.com/page"
        assert error.domain == "example.com"


class TestItemPageFetchError:
    """Tests for ItemPageFetchError."""

    def test_url_and_cause(self) -> None:
        """Test that URL and cause are stored."""
        original = ValueError("Network error")
        error = ItemPageFetchError(
            "Failed to fetch",
            url="https://example.com/article",
            cause=original,
        )
        assert error.url == "https://example.com/article"
        assert error.cause is original

    def test_without_cause(self) -> None:
        """Test without cause."""
        error = ItemPageFetchError(
            "Failed to fetch",
            url="https://example.com/article",
        )
        assert error.cause is None
