"""arXiv ID extraction and URL normalization utilities.

This module provides utilities for:
- Extracting arXiv IDs from various URL formats
- Normalizing arXiv URLs to canonical /abs/<id> format
- Supporting both old-style (e.g., hep-th/9901001) and new-style (e.g., 2401.12345) IDs
"""

import re
from urllib.parse import urlparse


# arXiv ID patterns
# New-style: YYMM.NNNNN (e.g., 2401.12345, 2401.12345v1)
NEW_STYLE_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")

# Old-style: archive/YYMMNNN (e.g., hep-th/9901001, cs.AI/0601001)
OLD_STYLE_ID_PATTERN = re.compile(
    r"([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.IGNORECASE
)

# Combined pattern for extracting from URLs
ARXIV_URL_PATTERN = re.compile(
    r"(?:arxiv\.org|ar5iv\.org|ar5iv\.labs\.arxiv\.org)"
    r"(?:/(?:abs|pdf|html|e-print|format|ps)/)?"
    r"([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})"
    r"(v\d+)?",
    re.IGNORECASE,
)

# Pattern for extracting ID from arXiv RSS entry ID field
RSS_ENTRY_ID_PATTERN = re.compile(
    r"(?:oai:arXiv\.org:|http://arxiv\.org/abs/)"
    r"([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})"
    r"(v\d+)?",
    re.IGNORECASE,
)


def extract_arxiv_id(url_or_id: str) -> str | None:
    """Extract arXiv ID from a URL or ID string.

    Supports various URL formats:
    - https://arxiv.org/abs/2401.12345
    - https://arxiv.org/abs/2401.12345v1
    - https://arxiv.org/pdf/2401.12345.pdf
    - https://ar5iv.labs.arxiv.org/html/2401.12345
    - http://arxiv.org/abs/hep-th/9901001
    - oai:arXiv.org:2401.12345 (RSS entry ID)

    Args:
        url_or_id: URL or arXiv ID string.

    Returns:
        Normalized arXiv ID without version suffix, or None if not found.
    """
    if not url_or_id:
        return None

    url_or_id = url_or_id.strip()

    # Try RSS entry ID format first
    rss_match = RSS_ENTRY_ID_PATTERN.search(url_or_id)
    if rss_match:
        return rss_match.group(1)

    # Try URL format
    url_match = ARXIV_URL_PATTERN.search(url_or_id)
    if url_match:
        return url_match.group(1)

    # Try direct new-style ID
    new_match = NEW_STYLE_ID_PATTERN.fullmatch(url_or_id.split("v")[0])
    if new_match:
        return new_match.group(1)

    # Try direct old-style ID
    old_match = OLD_STYLE_ID_PATTERN.fullmatch(url_or_id.split("v")[0])
    if old_match:
        return old_match.group(1)

    return None


def normalize_arxiv_url(url: str) -> str | None:
    """Normalize an arXiv URL to canonical format.

    Converts various arXiv URL formats to canonical:
    https://arxiv.org/abs/<id>

    Supported input formats:
    - https://arxiv.org/abs/2401.12345
    - https://arxiv.org/pdf/2401.12345.pdf
    - https://arxiv.org/html/2401.12345
    - https://ar5iv.labs.arxiv.org/html/2401.12345
    - http://arxiv.org/abs/hep-th/9901001

    Args:
        url: arXiv URL in any format.

    Returns:
        Canonical URL (https://arxiv.org/abs/<id>), or None if not an arXiv URL.
    """
    arxiv_id = extract_arxiv_id(url)
    if arxiv_id is None:
        return None

    return f"https://arxiv.org/abs/{arxiv_id}"


def is_arxiv_url(url: str) -> bool:
    """Check if a URL is an arXiv URL.

    Args:
        url: URL to check.

    Returns:
        True if the URL is an arXiv URL.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
        return parsed.netloc in (
            "arxiv.org",
            "www.arxiv.org",
            "ar5iv.org",
            "ar5iv.labs.arxiv.org",
            "export.arxiv.org",
        )
    except ValueError:
        return False


def get_arxiv_category_from_url(url: str) -> str | None:
    """Extract arXiv category from RSS feed URL.

    Args:
        url: arXiv RSS feed URL (e.g., https://rss.arxiv.org/rss/cs.AI)

    Returns:
        Category string (e.g., 'cs.AI'), or None if not an RSS feed URL.
    """
    if not url:
        return None

    # Match rss.arxiv.org/rss/<category> pattern
    match = re.search(r"rss\.arxiv\.org/rss/([a-z]+(?:\.[A-Z]+)?)", url, re.IGNORECASE)
    if match:
        return match.group(1)

    return None
