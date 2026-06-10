"""URL canonicalization utilities for the state store."""

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


# Default tracking parameters to strip (common across many sites)
DEFAULT_STRIP_PARAMS: list[str] = [
    # UTM parameters
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    # Social/sharing
    "fbclid",
    "gclid",
    "msclkid",
    "twclid",
    "igshid",
    # Analytics
    "_ga",
    "_gl",
    "mc_cid",
    "mc_eid",
    # Session/tracking
    "ref",
    "source",
    "via",
    "share",
    # Email tracking
    "mkt_tok",
    "trk",
]

# arXiv URL patterns for normalization
ARXIV_ABS_PATTERN = re.compile(r"^https?://arxiv\.org/abs/(\d+\.\d+(?:v\d+)?)$")
ARXIV_PDF_PATTERN = re.compile(r"^https?://arxiv\.org/pdf/(\d+\.\d+(?:v\d+)?)(\.pdf)?$")
ARXIV_HTML_PATTERN = re.compile(
    r"^https?://ar5iv\.labs\.arxiv\.org/html/(\d+\.\d+(?:v\d+)?)$"
)
ARXIV_OLD_ID_PATTERN = re.compile(r"^https?://arxiv\.org/abs/([a-z-]+/\d+(?:v\d+)?)$")


def canonicalize_url(
    url: str,
    strip_params: list[str] | None = None,
    preserve_fragments: bool = False,
) -> str:
    """Canonicalize a URL for deduplication.

    Canonicalization includes:
    - Lowercasing the scheme and host
    - Removing trailing slashes (except for root path)
    - Stripping tracking query parameters
    - Removing fragments (by default)
    - Normalizing arXiv URLs to /abs/ form

    Args:
        url: The URL to canonicalize.
        strip_params: List of query parameters to strip. If None, uses defaults.
        preserve_fragments: If True, keep URL fragments.

    Returns:
        Canonicalized URL string.
    """
    if not url:
        return url

    # Handle arXiv special cases first
    canonical = _normalize_arxiv_url(url)
    if canonical != url:
        url = canonical

    # Parse the URL
    parsed = urlparse(url)

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Upgrade http to https for known secure sites
    if scheme == "http" and _should_upgrade_to_https(netloc):
        scheme = "https"

    # Normalize path (remove trailing slash except for root)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Filter query parameters
    params_to_strip = strip_params if strip_params is not None else DEFAULT_STRIP_PARAMS
    query = _filter_query_params(parsed.query, params_to_strip)

    # Handle fragments
    fragment = parsed.fragment if preserve_fragments else ""

    # Reconstruct the URL
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def _normalize_arxiv_url(url: str) -> str:
    """Normalize arXiv URLs to canonical /abs/ form.

    Converts pdf, html, and ar5iv URLs to the standard /abs/ form.

    Args:
        url: The URL to normalize.

    Returns:
        Normalized arXiv URL or original URL if not arXiv.
    """
    # Check PDF pattern
    match = ARXIV_PDF_PATTERN.match(url)
    if match:
        arxiv_id = match.group(1)
        return f"https://arxiv.org/abs/{arxiv_id}"

    # Check ar5iv HTML pattern
    match = ARXIV_HTML_PATTERN.match(url)
    if match:
        arxiv_id = match.group(1)
        return f"https://arxiv.org/abs/{arxiv_id}"

    # Already in /abs/ form - ensure https
    match = ARXIV_ABS_PATTERN.match(url)
    if match:
        arxiv_id = match.group(1)
        return f"https://arxiv.org/abs/{arxiv_id}"

    # Old-style arXiv IDs (e.g., hep-ph/0001234)
    match = ARXIV_OLD_ID_PATTERN.match(url)
    if match:
        arxiv_id = match.group(1)
        return f"https://arxiv.org/abs/{arxiv_id}"

    return url


def _filter_query_params(query: str, strip_params: list[str]) -> str:
    """Filter out tracking parameters from query string.

    Args:
        query: Original query string.
        strip_params: List of parameter names to remove.

    Returns:
        Filtered query string.
    """
    if not query:
        return ""

    params = parse_qs(query, keep_blank_values=True)
    strip_set = {p.lower() for p in strip_params}

    filtered = {
        key: value for key, value in params.items() if key.lower() not in strip_set
    }

    if not filtered:
        return ""

    # Sort keys for deterministic output
    return urlencode(filtered, doseq=True, safe="")


def _should_upgrade_to_https(netloc: str) -> bool:
    """Check if a host should be upgraded to HTTPS.

    Args:
        netloc: The network location (host:port).

    Returns:
        True if the host should use HTTPS.
    """
    # List of known sites that support HTTPS
    https_hosts = {
        "arxiv.org",
        "github.com",
        "huggingface.co",
        "openreview.net",
        "paperswithcode.com",
        "aclanthology.org",
    }

    # Extract host without port
    host = netloc.split(":")[0]

    # Check exact match or subdomain
    for known_host in https_hosts:
        if host == known_host or host.endswith(f".{known_host}"):
            return True

    return False
