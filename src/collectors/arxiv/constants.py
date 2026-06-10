"""Constants for arXiv collectors.

Centralizes magic strings and configuration values used across
the arXiv collector modules.
"""

# Source type identifiers
SOURCE_TYPE_API = "api"
SOURCE_TYPE_RSS = "rss"

# Raw JSON field names
FIELD_SOURCE = "source"
FIELD_ARXIV_ID = "arxiv_id"
FIELD_CATEGORY = "category"
FIELD_MERGED_FROM_SOURCES = "merged_from_sources"
FIELD_SOURCE_IDS = "source_ids"
FIELD_TIMESTAMP_NOTE = "timestamp_note"

# Timestamp note messages
TIMESTAMP_NOTE_API_PREFERRED = "API and RSS timestamps differ; using API timestamp"

# arXiv API configuration
ARXIV_API_BASE_URL = "https://export.arxiv.org/api/query"
ARXIV_API_RATE_LIMIT_SECONDS = 30.0
ARXIV_API_DEFAULT_MAX_RESULTS = 1000
ARXIV_API_DEFAULT_SORT_BY = "submittedDate"
ARXIV_API_DEFAULT_SORT_ORDER = "descending"

# arXiv RSS feed URL pattern
ARXIV_RSS_BASE_URL = "https://rss.arxiv.org/rss"

# Canonical URL format
ARXIV_CANONICAL_URL_PREFIX = "https://arxiv.org/abs/"

# Deduplication thresholds
MIN_TIMESTAMPS_FOR_COMPARISON = 2
TIMESTAMP_DIFF_THRESHOLD_SECONDS = 86400  # 1 day
