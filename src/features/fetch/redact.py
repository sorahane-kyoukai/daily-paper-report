"""Header redaction utilities for logging."""

# Headers that must never appear in logs
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "x-api-key",
        "x-auth-token",
        "proxy-authorization",
        "set-cookie",
    }
)

REDACTED_VALUE = "[REDACTED]"


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive headers for logging.

    Replaces the values of Authorization, Cookie, and other
    sensitive headers with [REDACTED] for safe logging.

    Args:
        headers: Original headers dictionary.

    Returns:
        New dictionary with sensitive values redacted.
    """
    result: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            result[key] = REDACTED_VALUE
        else:
            result[key] = value
    return result


def is_sensitive_header(header_name: str) -> bool:
    """Check if a header name is sensitive.

    Args:
        header_name: The header name to check.

    Returns:
        True if the header should be redacted.
    """
    return header_name.lower() in SENSITIVE_HEADERS


def redact_url_credentials(url: str) -> str:
    """Redact credentials from a URL.

    Handles URLs like https://user:pass@example.com/path

    Args:
        url: URL that may contain credentials.

    Returns:
        URL with credentials redacted.
    """
    import re

    # Pattern matches user:password@ in URLs
    pattern = r"(https?://)([^:]+):([^@]+)@"
    return re.sub(pattern, r"\1[REDACTED]:[REDACTED]@", url)
