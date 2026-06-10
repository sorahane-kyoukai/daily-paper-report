"""Built-in domain profiles."""

from urllib.parse import urlparse

from src.collectors.html_profile.models import (
    DateExtractionRule,
    DomainProfile,
    LinkExtractionRule,
)


def get_builtin_profile_for_url(url: str) -> DomainProfile | None:
    """Return a built-in profile for known high-value HTML list pages."""
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path.rstrip("/") or "/"

    if domain in {"anthropic.com", "www.anthropic.com"} and path == "/research":
        return DomainProfile(
            domain="anthropic.com",
            name="Anthropic Research Publications",
            list_url_patterns=[r"https://(www\.)?anthropic\.com/research/?$"],
            link_rules=LinkExtractionRule(
                container_selector="[class*='PublicationList'] ul li",
                link_selector=(
                    "a[href^='/research/'], "
                    "a[href^='https://www.anthropic.com/research/'], "
                    "a[href^='https://anthropic.com/research/']"
                ),
                title_selectors=[
                    "span[class*='PublicationList'][class*='title']",
                    "span[class*='title']",
                    "h2",
                    "h3",
                    "h4",
                    "a",
                ],
                filter_patterns=[
                    r"/research/team/",
                    r"/careers",
                    r"/company",
                    r"/news",
                    r"/economic-futures",
                ],
            ),
            date_rules=DateExtractionRule(time_selector="time"),
            enable_item_page_recovery=False,
            max_item_page_fetches=0,
        )

    return None


__all__ = ["get_builtin_profile_for_url"]
