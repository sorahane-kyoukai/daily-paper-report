"""Story ID generation for deterministic identification."""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from src.features.store.models import Item
from src.linker.constants import (
    ARXIV_ID_PATTERN,
    DATE_BUCKET_FORMAT,
    GITHUB_RELEASE_PATTERN,
    HF_MODEL_ID_PATTERN,
    MAX_TITLE_LENGTH,
    MODELSCOPE_ID_PATTERN,
    TITLE_STRIP_CHARS,
)


def extract_arxiv_id(url: str) -> str | None:
    """Extract arXiv ID from URL or raw text.

    Args:
        url: URL or text containing arXiv ID.

    Returns:
        arXiv ID if found, None otherwise.
    """
    match = ARXIV_ID_PATTERN.search(url)
    if match:
        arxiv_id = match.group("id")
        # Normalize: remove version suffix for deduplication
        return re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
    return None


def extract_hf_model_id(url: str) -> str | None:
    """Extract Hugging Face model ID from URL.

    Args:
        url: URL containing HF model page.

    Returns:
        Model ID (org/model) if found, None otherwise.
    """
    match = HF_MODEL_ID_PATTERN.search(url)
    if match:
        return match.group("id").lower()
    return None


def extract_github_release_id(url: str) -> str | None:
    """Extract GitHub release identifier from URL.

    Args:
        url: URL containing GitHub release.

    Returns:
        Release identifier (repo/tag) if found, None otherwise.
    """
    match = GITHUB_RELEASE_PATTERN.search(url)
    if match:
        repo = match.group("repo").lower()
        tag = match.group("tag").lower()
        return f"{repo}:{tag}"
    return None


def extract_modelscope_id(url: str) -> str | None:
    """Extract ModelScope model ID from URL.

    Args:
        url: URL containing ModelScope model page.

    Returns:
        Model ID if found, None otherwise.
    """
    match = MODELSCOPE_ID_PATTERN.search(url)
    if match:
        return match.group("id").lower()
    return None


def normalize_title(title: str) -> str:
    """Normalize title for fallback story_id generation.

    Args:
        title: Raw title string.

    Returns:
        Normalized title suitable for ID generation.
    """
    # Normalize unicode (decompose accents)
    normalized = unicodedata.normalize("NFKD", title)

    # Convert to lowercase
    normalized = normalized.lower()

    # Remove special characters
    for char in TITLE_STRIP_CHARS:
        normalized = normalized.replace(char, "")

    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Truncate
    if len(normalized) > MAX_TITLE_LENGTH:
        normalized = normalized[:MAX_TITLE_LENGTH]

    return normalized


def get_date_bucket(dt: datetime | None) -> str:
    """Get date bucket string for story_id.

    Args:
        dt: Datetime to bucket.

    Returns:
        Date bucket string (YYYY-MM-DD) or 'unknown'.
    """
    if dt is None:
        return "unknown"
    return dt.strftime(DATE_BUCKET_FORMAT)


def extract_stable_id(item: Item) -> tuple[str | None, str]:
    """Extract stable ID from an item.

    Priority order:
    1. arXiv ID
    2. GitHub release URL
    3. HF model ID
    4. ModelScope ID

    Args:
        item: Item to extract stable ID from.

    Returns:
        Tuple of (stable_id, id_type) where id_type is one of:
        'arxiv', 'github', 'huggingface', 'modelscope', or 'none'.
    """
    # Check arXiv ID
    arxiv_id = extract_arxiv_id(item.url)
    if arxiv_id:
        return f"arxiv:{arxiv_id}", "arxiv"

    # Check raw_json for arXiv ID field
    try:
        raw = json.loads(item.raw_json)
        if arxiv_id_field := raw.get("arxiv_id"):
            return f"arxiv:{arxiv_id_field}", "arxiv"
    except (json.JSONDecodeError, KeyError):
        pass

    # Check GitHub release
    github_id = extract_github_release_id(item.url)
    if github_id:
        return f"github:{github_id}", "github"

    # Check HF model ID
    hf_id = extract_hf_model_id(item.url)
    if hf_id:
        return f"hf:{hf_id}", "huggingface"

    # Check ModelScope ID
    ms_id = extract_modelscope_id(item.url)
    if ms_id:
        return f"ms:{ms_id}", "modelscope"

    return None, "none"


@dataclass
class ExtractedStableIds:
    """Collection of extracted stable IDs from items.

    Attributes:
        arxiv_id: arXiv paper ID if found.
        hf_model_id: HuggingFace model ID if found.
        github_release_url: GitHub release URL if found.
        modelscope_id: ModelScope model ID if found.
    """

    arxiv_id: str | None = None
    hf_model_id: str | None = None
    github_release_url: str | None = None
    modelscope_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary with only non-None values."""
        result: dict[str, str] = {}
        if self.arxiv_id:
            result["arxiv_id"] = self.arxiv_id
        if self.hf_model_id:
            result["hf_model_id"] = self.hf_model_id
        if self.github_release_url:
            result["github_release_url"] = self.github_release_url
        if self.modelscope_id:
            result["modelscope_id"] = self.modelscope_id
        return result


def extract_all_stable_ids(items: list[Item]) -> ExtractedStableIds:
    """Extract all stable IDs from a list of items.

    Scans all items and returns the first found ID of each type.

    Args:
        items: Items to scan.

    Returns:
        ExtractedStableIds with all found IDs.
    """
    arxiv_id: str | None = None
    hf_model_id: str | None = None
    github_release_url: str | None = None
    modelscope_id: str | None = None

    for item in items:
        if not arxiv_id:
            arxiv_id = extract_arxiv_id(item.url)
        if not hf_model_id:
            hf_model_id = extract_hf_model_id(item.url)
        if not github_release_url:
            github_id = extract_github_release_id(item.url)
            if github_id:
                github_release_url = item.url
        if not modelscope_id:
            modelscope_id = extract_modelscope_id(item.url)

    return ExtractedStableIds(
        arxiv_id=arxiv_id,
        hf_model_id=hf_model_id,
        github_release_url=github_release_url,
        modelscope_id=modelscope_id,
    )


def generate_story_id(
    items: list[Item],
    entity_ids: list[str] | None = None,
) -> tuple[str, str]:
    """Generate deterministic story_id for a group of items.

    Priority order:
    1. arXiv ID (if any item has one)
    2. GitHub release URL
    3. HF model ID
    4. Fallback: hash of normalized(title) + entity_id + date_bucket

    Args:
        items: Items to generate story_id for.
        entity_ids: Matched entity IDs (used in fallback).

    Returns:
        Tuple of (story_id, id_type).
    """
    if not items:
        msg = "Cannot generate story_id for empty item list"
        raise ValueError(msg)

    # Try to extract stable ID from any item
    for item in items:
        stable_id, id_type = extract_stable_id(item)
        if stable_id:
            return stable_id, id_type

    # Fallback: use normalized title + entity + date bucket
    first_item = items[0]
    normalized = normalize_title(first_item.title)

    # Use first entity if available
    entity_part = entity_ids[0] if entity_ids else "unknown"

    # Use date bucket from best available date
    date_bucket = "unknown"
    for item in items:
        if item.published_at:
            date_bucket = get_date_bucket(item.published_at)
            break

    # Create deterministic hash
    content = f"{normalized}|{entity_part}|{date_bucket}"
    hash_val = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    return f"fallback:{hash_val}", "fallback"
