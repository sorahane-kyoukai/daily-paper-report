"""Constants for the Story linker."""

import re


# arXiv ID pattern: new format (YYMM.NNNNN) or old format (archive/YYMMNNN)
ARXIV_ID_PATTERN = re.compile(
    r"(?:arxiv(?:\.org)?[:/])?(?:abs/|pdf/)?"
    r"(?P<id>(?:\d{4}\.\d{4,5}(?:v\d+)?)|(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?))",
    re.IGNORECASE,
)

# Hugging Face model ID pattern: org/model-name
HF_MODEL_ID_PATTERN = re.compile(
    r"huggingface\.co/(?P<id>[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+)", re.IGNORECASE
)

# GitHub release URL pattern
GITHUB_RELEASE_PATTERN = re.compile(
    r"github\.com/(?P<repo>[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+)/releases/(?:tag/)?(?P<tag>[^/\s]+)",
    re.IGNORECASE,
)

# ModelScope model ID pattern
MODELSCOPE_ID_PATTERN = re.compile(
    r"modelscope\.cn/models/(?P<id>[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+)", re.IGNORECASE
)

# Allowlisted link types for primary link selection
ALLOWLISTED_LINK_TYPES = frozenset(
    [
        "official",
        "arxiv",
        "github",
        "huggingface",
        "modelscope",
        "openreview",
        "paper",
        "blog",
        "docs",
    ]
)

# Default primary link precedence order (as strings for flexibility)
DEFAULT_PRIMARY_LINK_ORDER: list[str] = [
    "official",
    "arxiv",
    "github",
    "huggingface",
    "paper",
    "blog",
]

# Date bucket format for fallback story_id
DATE_BUCKET_FORMAT = "%Y-%m-%d"

# Maximum title length for normalization
MAX_TITLE_LENGTH = 100

# Characters to strip from titles for normalization
TITLE_STRIP_CHARS = "!@#$%^&*()[]{}|\\;:'\",.<>?/`~"

# Field names for raw_json
FIELD_LINKER_MERGE_COUNT = "_linker_merge_count"
FIELD_LINKER_SOURCE_IDS = "_linker_source_ids"
FIELD_LINKER_STABLE_ID = "_linker_stable_id"
FIELD_LINKER_STABLE_ID_TYPE = "_linker_stable_id_type"
