"""HTML domain profile system for stable list and article parsing."""

from src.collectors.html_profile.date_extractor import (
    DateExtractionResult,
    DateExtractor,
)
from src.collectors.html_profile.exceptions import (
    ContentTypeError,
    CrossDomainRedirectError,
    DateExtractionError,
    HtmlProfileError,
    ItemPageFetchError,
    ProfileNotFoundError,
)
from src.collectors.html_profile.item_fetcher import ItemPageFetcher
from src.collectors.html_profile.loader import (
    load_profiles_from_directory,
    load_profiles_from_yaml,
)
from src.collectors.html_profile.metrics import HtmlProfileMetrics
from src.collectors.html_profile.models import (
    DateExtractionMethod,
    DateExtractionRule,
    DomainProfile,
    LinkExtractionRule,
)
from src.collectors.html_profile.registry import ProfileRegistry
from src.collectors.html_profile.utils import RegexCache, compile_regex


__all__ = [
    # Exceptions
    "ContentTypeError",
    "CrossDomainRedirectError",
    "DateExtractionError",
    "HtmlProfileError",
    "ItemPageFetchError",
    "ProfileNotFoundError",
    # Core types
    "DateExtractionMethod",
    "DateExtractionResult",
    "DateExtractionRule",
    "DateExtractor",
    "DomainProfile",
    "HtmlProfileMetrics",
    "ItemPageFetcher",
    "LinkExtractionRule",
    "ProfileRegistry",
    # Utilities
    "RegexCache",
    "compile_regex",
    "load_profiles_from_directory",
    "load_profiles_from_yaml",
]
