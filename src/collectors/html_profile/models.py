"""Domain profile models for HTML list and article parsing."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DateExtractionMethod(str, Enum):
    """Method used to extract dates.

    Ordered by precedence (highest to lowest):
    - TIME_ELEMENT: <time datetime="...">
    - META_PUBLISHED_TIME: <meta property="article:published_time">
    - JSON_LD: JSON-LD Article.datePublished
    - TEXT_PATTERN: Regex pattern match in text
    - NONE: No date could be extracted
    """

    TIME_ELEMENT = "time_element"
    META_PUBLISHED_TIME = "meta_published_time"
    JSON_LD = "json_ld"
    TEXT_PATTERN = "text_pattern"
    NONE = "none"


class LinkExtractionRule(BaseModel):
    """Rule for extracting links from an HTML list page.

    Attributes:
        container_selector: CSS selector for item containers.
        link_selector: CSS selector for links within containers.
        title_selectors: List of selectors to try for title extraction.
        filter_patterns: Regex patterns for URLs to exclude.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    container_selector: str = Field(
        default="article",
        description="CSS selector for item containers",
    )
    link_selector: str = Field(
        default="a[href]",
        description="CSS selector for links within containers",
    )
    title_selectors: list[str] = Field(
        default_factory=lambda: ["h1", "h2", "h3", "h4", ".title", ".headline"],
        description="CSS selectors to try for title extraction",
    )
    filter_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns for URLs to exclude",
    )


class DateExtractionRule(BaseModel):
    """Rule for extracting dates from HTML.

    Attributes:
        time_selector: CSS selector for <time> elements.
        meta_properties: Meta tag properties to check for dates.
        json_ld_keys: JSON-LD keys to check for dates.
        text_patterns: Regex patterns for date extraction from text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    time_selector: str = Field(
        default="time[datetime]",
        description="CSS selector for <time> elements",
    )
    meta_properties: list[str] = Field(
        default_factory=lambda: [
            "article:published_time",
            "og:article:published_time",
            "datePublished",
        ],
        description="Meta tag properties to check for dates",
    )
    json_ld_keys: list[str] = Field(
        default_factory=lambda: ["datePublished", "dateCreated", "dateModified"],
        description="JSON-LD keys to check for dates",
    )
    text_patterns: list[str] = Field(
        default_factory=lambda: [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{4}/\d{2}/\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4}",
            r"\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}",
        ],
        description="Regex patterns for date extraction from text",
    )


class DomainProfile(BaseModel):
    """Profile configuration for a specific domain.

    Defines extraction rules, URL normalization, and security settings
    for parsing HTML list pages from a domain.

    Attributes:
        domain: Domain name (e.g., "openai.com").
        name: Human-readable name for the profile.
        list_url_patterns: Regex patterns matching list page URLs.
        link_rules: Rules for extracting links.
        date_rules: Rules for extracting dates.
        canonical_url_strip_params: URL parameters to strip.
        canonical_url_preserve_fragment: Whether to keep URL fragments.
        allowed_redirect_domains: Domains allowed for cross-domain redirects.
        max_item_page_fetches: Max item pages to fetch per run (K-cap).
        enable_item_page_recovery: Whether to fetch item pages for date recovery.
        allowed_content_types: Content types to accept.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: Annotated[str, Field(min_length=1, description="Domain name")]
    name: Annotated[str, Field(min_length=1, description="Human-readable profile name")]

    list_url_patterns: list[str] = Field(
        default_factory=lambda: [".*"],
        description="Regex patterns matching list page URLs",
    )

    link_rules: LinkExtractionRule = Field(
        default_factory=LinkExtractionRule,
        description="Rules for extracting links",
    )

    date_rules: DateExtractionRule = Field(
        default_factory=DateExtractionRule,
        description="Rules for extracting dates",
    )

    canonical_url_strip_params: list[str] = Field(
        default_factory=lambda: [
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "ref",
            "fbclid",
            "gclid",
        ],
        description="URL parameters to strip for canonicalization",
    )

    canonical_url_preserve_fragment: bool = Field(
        default=False,
        description="Whether to preserve URL fragments",
    )

    allowed_redirect_domains: list[str] = Field(
        default_factory=list,
        description="Domains allowed for cross-domain redirects",
    )

    max_item_page_fetches: Annotated[int, Field(ge=0, le=50)] = Field(
        default=10,
        description="Maximum item pages to fetch per run for date recovery (K-cap)",
    )

    enable_item_page_recovery: bool = Field(
        default=True,
        description="Whether to fetch item pages for date recovery",
    )

    allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "text/html",
            "application/xhtml+xml",
            "application/xml",
        ],
        description="Content types to accept",
    )

    def matches_url(self, url: str) -> bool:
        """Check if this profile matches the given URL.

        Args:
            url: URL to check.

        Returns:
            True if the profile matches the URL.
        """
        import re
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Check domain
        if parsed.netloc != self.domain and not parsed.netloc.endswith(
            f".{self.domain}"
        ):
            return False

        # Check URL patterns
        return any(re.match(pattern, url) for pattern in self.list_url_patterns)

    def is_redirect_allowed(self, from_domain: str, to_domain: str) -> bool:
        """Check if a cross-domain redirect is allowed.

        Args:
            from_domain: Original domain.
            to_domain: Redirect target domain.

        Returns:
            True if the redirect is allowed.
        """
        # Same domain is always allowed
        if from_domain == to_domain:
            return True

        # Subdomain of same base domain is allowed
        if to_domain.endswith(f".{from_domain}") or from_domain.endswith(
            f".{to_domain}"
        ):
            return True

        # Check allowlist
        return to_domain in self.allowed_redirect_domains

    def is_content_type_allowed(self, content_type: str) -> bool:
        """Check if a content type is allowed.

        Args:
            content_type: Content-Type header value.

        Returns:
            True if the content type is allowed.
        """
        # Extract MIME type without parameters
        mime_type = content_type.split(";")[0].strip().lower()

        return mime_type in self.allowed_content_types
