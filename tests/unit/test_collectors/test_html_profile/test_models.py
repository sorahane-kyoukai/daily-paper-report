"""Tests for domain profile models."""

import pytest

from src.collectors.html_profile.models import (
    DateExtractionMethod,
    DateExtractionRule,
    DomainProfile,
    LinkExtractionRule,
)


class TestDomainProfile:
    """Tests for DomainProfile model."""

    def test_create_minimal_profile(self) -> None:
        """Test creating a minimal profile."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert profile.domain == "example.com"
        assert profile.name == "Example Profile"
        assert profile.max_item_page_fetches == 10
        assert profile.enable_item_page_recovery is True

    def test_matches_url_same_domain(self) -> None:
        """Test URL matching for same domain."""
        profile = DomainProfile(domain="blog.example.com", name="Blog Profile")

        assert profile.matches_url("https://blog.example.com/posts")
        assert profile.matches_url("https://blog.example.com/articles/123")

    def test_matches_url_subdomain(self) -> None:
        """Test URL matching for subdomain."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        # Subdomain should match parent domain profile
        assert profile.matches_url("https://blog.example.com/posts")
        assert profile.matches_url("https://www.example.com/articles")

    def test_matches_url_different_domain(self) -> None:
        """Test URL matching for different domain."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert not profile.matches_url("https://other.com/posts")
        assert not profile.matches_url("https://notexample.com/articles")

    def test_matches_url_with_patterns(self) -> None:
        """Test URL matching with specific patterns."""
        profile = DomainProfile(
            domain="example.com",
            name="Example Profile",
            list_url_patterns=[r".*\/blog\/.*", r".*\/news\/.*"],
        )

        assert profile.matches_url("https://example.com/blog/posts")
        assert profile.matches_url("https://example.com/news/latest")

    def test_is_redirect_allowed_same_domain(self) -> None:
        """Test redirect allowed for same domain."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert profile.is_redirect_allowed("example.com", "example.com")

    def test_is_redirect_allowed_subdomain(self) -> None:
        """Test redirect allowed for subdomain."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert profile.is_redirect_allowed("example.com", "www.example.com")
        assert profile.is_redirect_allowed("example.com", "blog.example.com")
        assert profile.is_redirect_allowed("blog.example.com", "example.com")

    def test_is_redirect_blocked_unknown_domain(self) -> None:
        """Test redirect blocked for unknown domain."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert not profile.is_redirect_allowed("example.com", "malicious.com")
        assert not profile.is_redirect_allowed("example.com", "other-site.com")

    def test_is_redirect_allowed_allowlisted_domain(self) -> None:
        """Test redirect allowed for allowlisted domain."""
        profile = DomainProfile(
            domain="example.com",
            name="Example Profile",
            allowed_redirect_domains=["cdn.example.com", "trusted-partner.com"],
        )

        assert profile.is_redirect_allowed("example.com", "cdn.example.com")
        assert profile.is_redirect_allowed("example.com", "trusted-partner.com")
        assert not profile.is_redirect_allowed("example.com", "not-trusted.com")

    def test_is_content_type_allowed_html(self) -> None:
        """Test content type validation for HTML."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert profile.is_content_type_allowed("text/html")
        assert profile.is_content_type_allowed("text/html; charset=utf-8")
        assert profile.is_content_type_allowed("application/xhtml+xml")

    def test_is_content_type_blocked_binary(self) -> None:
        """Test content type validation blocks binary."""
        profile = DomainProfile(domain="example.com", name="Example Profile")

        assert not profile.is_content_type_allowed("image/png")
        assert not profile.is_content_type_allowed("video/mp4")
        assert not profile.is_content_type_allowed("application/pdf")
        assert not profile.is_content_type_allowed("application/octet-stream")

    def test_custom_content_types(self) -> None:
        """Test custom allowed content types."""
        profile = DomainProfile(
            domain="example.com",
            name="Example Profile",
            allowed_content_types=["text/html", "application/json"],
        )

        assert profile.is_content_type_allowed("text/html")
        assert profile.is_content_type_allowed("application/json")
        assert not profile.is_content_type_allowed("application/xml")

    def test_k_cap_validation(self) -> None:
        """Test K-cap (max_item_page_fetches) validation."""
        # Valid range
        profile = DomainProfile(
            domain="example.com",
            name="Example Profile",
            max_item_page_fetches=5,
        )
        assert profile.max_item_page_fetches == 5

        # Edge cases
        profile_zero = DomainProfile(
            domain="example.com",
            name="Example Profile",
            max_item_page_fetches=0,
        )
        assert profile_zero.max_item_page_fetches == 0

        profile_max = DomainProfile(
            domain="example.com",
            name="Example Profile",
            max_item_page_fetches=50,
        )
        assert profile_max.max_item_page_fetches == 50

    def test_k_cap_validation_out_of_range(self) -> None:
        """Test K-cap validation rejects out of range values."""
        with pytest.raises(ValueError):
            DomainProfile(
                domain="example.com",
                name="Example Profile",
                max_item_page_fetches=-1,
            )

        with pytest.raises(ValueError):
            DomainProfile(
                domain="example.com",
                name="Example Profile",
                max_item_page_fetches=51,
            )


class TestLinkExtractionRule:
    """Tests for LinkExtractionRule model."""

    def test_default_values(self) -> None:
        """Test default values."""
        rule = LinkExtractionRule()

        assert rule.container_selector == "article"
        assert rule.link_selector == "a[href]"
        assert len(rule.title_selectors) > 0
        assert "h1" in rule.title_selectors

    def test_custom_selectors(self) -> None:
        """Test custom selectors."""
        rule = LinkExtractionRule(
            container_selector=".blog-post",
            link_selector="a.post-link",
            title_selectors=[".post-title", "h2"],
            filter_patterns=[r"/tag/", r"/category/"],
        )

        assert rule.container_selector == ".blog-post"
        assert rule.link_selector == "a.post-link"
        assert rule.title_selectors == [".post-title", "h2"]
        assert "/tag/" in rule.filter_patterns[0]


class TestDateExtractionRule:
    """Tests for DateExtractionRule model."""

    def test_default_values(self) -> None:
        """Test default values."""
        rule = DateExtractionRule()

        assert rule.time_selector == "time[datetime]"
        assert "article:published_time" in rule.meta_properties
        assert "datePublished" in rule.json_ld_keys
        assert len(rule.text_patterns) > 0

    def test_custom_rules(self) -> None:
        """Test custom rules."""
        rule = DateExtractionRule(
            time_selector=".date[datetime]",
            meta_properties=["custom:date"],
            json_ld_keys=["datePublished", "createdAt"],
            text_patterns=[r"\d{4}-\d{2}-\d{2}"],
        )

        assert rule.time_selector == ".date[datetime]"
        assert rule.meta_properties == ["custom:date"]
        assert "createdAt" in rule.json_ld_keys


class TestDateExtractionMethod:
    """Tests for DateExtractionMethod enum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert DateExtractionMethod.TIME_ELEMENT.value == "time_element"
        assert DateExtractionMethod.META_PUBLISHED_TIME.value == "meta_published_time"
        assert DateExtractionMethod.JSON_LD.value == "json_ld"
        assert DateExtractionMethod.TEXT_PATTERN.value == "text_pattern"
        assert DateExtractionMethod.NONE.value == "none"
