"""Content hashing utilities for the state store.

This module provides deterministic content hashing for item deduplication
and change detection.
"""

import hashlib
from datetime import datetime


def compute_content_hash(
    title: str,
    url: str,
    published_at: datetime | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """Compute a content hash for an item.

    Creates a deterministic hash from item content for detecting changes.
    The hash is based on normalized title, canonical URL, optional publish date,
    and any extra fields provided.

    Args:
        title: Item title (will be stripped and lowercased for normalization).
        url: Canonical URL (should already be canonicalized).
        published_at: Optional publication timestamp.
        extra: Optional extra fields to include in the hash.

    Returns:
        First 16 characters of SHA-256 hash of normalized content.

    Examples:
        >>> compute_content_hash("My Article", "https://example.com/article")
        'a1b2c3d4e5f6g7h8'

        >>> compute_content_hash(
        ...     "My Article",
        ...     "https://example.com/article",
        ...     extra={"author": "John Doe"},
        ... )
        'x9y8z7w6v5u4t3s2'
    """
    parts = [
        f"title:{title.strip().lower()}",
        f"url:{url}",
    ]

    if published_at:
        parts.append(f"published_at:{published_at.isoformat()}")

    if extra:
        for key, value in sorted(extra.items()):
            parts.append(f"{key}:{value}")

    content = "\n".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
