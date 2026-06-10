"""Secret redaction utilities for evidence files."""

import re
from typing import NamedTuple


# Patterns that indicate potential secrets
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Google OAuth tokens
    ("google_oauth_access", re.compile(r"\bya29\.[a-zA-Z0-9_\-\.]+\b")),
    ("google_oauth_refresh", re.compile(r"\b1//[a-zA-Z0-9_\-]+\b")),
    # API keys with common prefixes
    ("api_key_sk", re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b")),
    ("api_key_pk", re.compile(r"\bpk-[a-zA-Z0-9]{20,}\b")),
    ("api_key_generic", re.compile(r"\bkey-[a-zA-Z0-9]{20,}\b")),
    # Bearer tokens
    ("bearer_token", re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]+\b", re.IGNORECASE)),
    # GitHub tokens
    ("github_token", re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b")),
    ("github_classic", re.compile(r"\bghp_[a-zA-Z0-9]{36}\b")),
    # HuggingFace tokens
    ("hf_token", re.compile(r"\bhf_[a-zA-Z0-9]{34,}\b")),
    # Generic secrets in key=value format
    (
        "password_value",
        re.compile(r"\bpassword\s*[=:]\s*['\"]?[^\s'\"]{8,}['\"]?", re.IGNORECASE),
    ),
    (
        "secret_value",
        re.compile(r"\bsecret\s*[=:]\s*['\"]?[^\s'\"]{8,}['\"]?", re.IGNORECASE),
    ),
    (
        "token_value",
        re.compile(r"\btoken\s*[=:]\s*['\"]?[^\s'\"]{20,}['\"]?", re.IGNORECASE),
    ),
    # AWS keys
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret_key", re.compile(r"\b[a-zA-Z0-9/+=]{40}\b")),
    # Base64 encoded long strings (potential encoded secrets)
    ("base64_long", re.compile(r"\b[a-zA-Z0-9+/]{50,}={0,2}\b")),
    # Authorization headers
    ("auth_header", re.compile(r"Authorization:\s*[^\n]+", re.IGNORECASE)),
    # Cookie headers
    ("cookie_header", re.compile(r"Cookie:\s*[^\n]+", re.IGNORECASE)),
    # Set-Cookie headers
    ("set_cookie_header", re.compile(r"Set-Cookie:\s*[^\n]+", re.IGNORECASE)),
]

REDACTED_VALUE = "[REDACTED]"


class SecretMatch(NamedTuple):
    """Represents a detected secret in content."""

    pattern_name: str
    matched_text: str
    start: int
    end: int


def scan_for_secrets(content: str) -> list[SecretMatch]:
    """Scan content for potential secrets.

    Args:
        content: Text content to scan.

    Returns:
        List of SecretMatch objects for each detected secret.
    """
    matches: list[SecretMatch] = []
    for pattern_name, pattern in SECRET_PATTERNS:
        matches.extend(
            SecretMatch(
                pattern_name=pattern_name,
                matched_text=match.group(),
                start=match.start(),
                end=match.end(),
            )
            for match in pattern.finditer(content)
        )
    return matches


def redact_content(content: str) -> str:
    """Redact secrets from content.

    Replaces detected secrets with [REDACTED].

    Args:
        content: Text content to redact.

    Returns:
        Content with secrets redacted.
    """
    result = content
    for _, pattern in SECRET_PATTERNS:
        result = pattern.sub(REDACTED_VALUE, result)
    return result


def contains_secrets(content: str) -> bool:
    """Check if content contains any secrets.

    Args:
        content: Text content to check.

    Returns:
        True if secrets are detected, False otherwise.
    """
    return len(scan_for_secrets(content)) > 0


def get_secret_patterns() -> list[str]:
    """Get list of secret pattern names.

    Returns:
        List of pattern names used for detection.
    """
    return [name for name, _ in SECRET_PATTERNS]
