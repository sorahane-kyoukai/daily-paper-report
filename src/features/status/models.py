"""Models for source status classification and reporting."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ReasonCode(str, Enum):
    """Machine-readable reason codes for source status.

    Each code maps to a human-readable reason_text.
    Codes are designed to be stable across runs for identical conditions.
    """

    # Success states
    FETCH_PARSE_OK_HAS_NEW = "FETCH_PARSE_OK_HAS_NEW"
    FETCH_PARSE_OK_HAS_UPDATED = "FETCH_PARSE_OK_HAS_UPDATED"
    FETCH_PARSE_OK_NO_DELTA = "FETCH_PARSE_OK_NO_DELTA"

    # Status-only source
    STATUS_ONLY_SOURCE = "STATUS_ONLY_SOURCE"

    # Cannot confirm states
    DATES_MISSING_NO_ORDERING = "DATES_MISSING_NO_ORDERING"
    DYNAMIC_CONTENT_DETECTED = "DYNAMIC_CONTENT_DETECTED"

    # Failure states
    FETCH_TIMEOUT = "FETCH_TIMEOUT"
    FETCH_HTTP_4XX = "FETCH_HTTP_4XX"
    FETCH_HTTP_5XX = "FETCH_HTTP_5XX"
    FETCH_NETWORK_ERROR = "FETCH_NETWORK_ERROR"
    FETCH_SSL_ERROR = "FETCH_SSL_ERROR"
    FETCH_TOO_LARGE = "FETCH_TOO_LARGE"

    PARSE_XML_ERROR = "PARSE_XML_ERROR"
    PARSE_HTML_ERROR = "PARSE_HTML_ERROR"
    PARSE_JSON_ERROR = "PARSE_JSON_ERROR"
    PARSE_SCHEMA_ERROR = "PARSE_SCHEMA_ERROR"
    PARSE_NO_ITEMS = "PARSE_NO_ITEMS"

    # Unknown/fallback
    UNKNOWN = "UNKNOWN"


# Mapping from reason code to human-readable text
REASON_TEXT_MAP: dict[ReasonCode, str] = {
    ReasonCode.FETCH_PARSE_OK_HAS_NEW: "Fetch and parse succeeded; new items found.",
    ReasonCode.FETCH_PARSE_OK_HAS_UPDATED: "Fetch and parse succeeded; items updated.",
    ReasonCode.FETCH_PARSE_OK_NO_DELTA: "Fetch and parse succeeded; no changes since last run.",
    ReasonCode.STATUS_ONLY_SOURCE: "Source is status-only; no items expected.",
    ReasonCode.DATES_MISSING_NO_ORDERING: "Published dates missing for all items; cannot confirm update status.",
    ReasonCode.DYNAMIC_CONTENT_DETECTED: "Source content is dynamic; update status cannot be reliably determined.",
    ReasonCode.FETCH_TIMEOUT: "HTTP fetch timed out.",
    ReasonCode.FETCH_HTTP_4XX: "HTTP fetch failed with client error (4xx).",
    ReasonCode.FETCH_HTTP_5XX: "HTTP fetch failed with server error (5xx).",
    ReasonCode.FETCH_NETWORK_ERROR: "Network error during fetch.",
    ReasonCode.FETCH_SSL_ERROR: "SSL/TLS error during fetch.",
    ReasonCode.FETCH_TOO_LARGE: "Response exceeded maximum size limit.",
    ReasonCode.PARSE_XML_ERROR: "Failed to parse XML content.",
    ReasonCode.PARSE_HTML_ERROR: "Failed to parse HTML content.",
    ReasonCode.PARSE_JSON_ERROR: "Failed to parse JSON content.",
    ReasonCode.PARSE_SCHEMA_ERROR: "Content does not match expected schema.",
    ReasonCode.PARSE_NO_ITEMS: "Parse succeeded but no items found.",
    ReasonCode.UNKNOWN: "Status could not be determined.",
}

# Mapping from reason code to optional remediation hint
REMEDIATION_HINT_MAP: dict[ReasonCode, str | None] = {
    ReasonCode.FETCH_TIMEOUT: "Consider increasing timeout or checking network connectivity.",
    ReasonCode.FETCH_HTTP_4XX: "Check URL validity, authentication, or rate limiting.",
    ReasonCode.FETCH_HTTP_5XX: "Server error; retry later or contact source administrator.",
    ReasonCode.FETCH_NETWORK_ERROR: "Check network connectivity and DNS resolution.",
    ReasonCode.FETCH_SSL_ERROR: "Check SSL certificate validity or consider allowing insecure connections.",
    ReasonCode.FETCH_TOO_LARGE: "Consider filtering content or increasing size limit.",
    ReasonCode.PARSE_XML_ERROR: "Source may have changed format; update parser.",
    ReasonCode.PARSE_HTML_ERROR: "Source HTML structure may have changed; update selectors.",
    ReasonCode.PARSE_JSON_ERROR: "Source JSON format may have changed; update schema.",
    ReasonCode.PARSE_SCHEMA_ERROR: "Expected data structure changed; update schema.",
    ReasonCode.DATES_MISSING_NO_ORDERING: "Consider using item page date recovery or stable identifiers.",
}


class SourceCategory(str, Enum):
    """Category for grouping sources in UI.

    Sources are grouped by:
    - INTL_LABS: International research labs (e.g., OpenAI, Google, Anthropic)
    - CN_ECOSYSTEM: Chinese/CN ecosystem (e.g., Alibaba, Baidu, Tencent)
    - PLATFORMS: Development platforms (e.g., HuggingFace, GitHub, OpenReview)
    - PAPER_SOURCES: Academic paper sources (e.g., arXiv)
    - OTHER: Uncategorized sources
    """

    INTL_LABS = "intl_labs"
    CN_ECOSYSTEM = "cn_ecosystem"
    PLATFORMS = "platforms"
    PAPER_SOURCES = "paper_sources"
    OTHER = "other"


# Human-readable category names for display
CATEGORY_DISPLAY_NAMES: dict[SourceCategory, str] = {
    SourceCategory.INTL_LABS: "International Labs",
    SourceCategory.CN_ECOSYSTEM: "CN / Chinese Ecosystem",
    SourceCategory.PLATFORMS: "Platforms",
    SourceCategory.PAPER_SOURCES: "Paper Sources",
    SourceCategory.OTHER: "Other",
}


class StatusSummary(BaseModel):
    """Pre-computed summary statistics for source statuses.

    This model encapsulates all summary counts for efficient
    template rendering without inline computation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total: Annotated[int, Field(ge=0)]
    has_update: Annotated[int, Field(ge=0)]
    no_update: Annotated[int, Field(ge=0)]
    fetch_failed: Annotated[int, Field(ge=0)]
    parse_failed: Annotated[int, Field(ge=0)]
    cannot_confirm: Annotated[int, Field(ge=0)]
    status_only: Annotated[int, Field(ge=0)]

    @property
    def failed_total(self) -> int:
        """Total count of failed sources (fetch + parse)."""
        return self.fetch_failed + self.parse_failed

    @property
    def success_rate(self) -> float:
        """Percentage of sources that succeeded (has_update + no_update)."""
        if self.total == 0:
            return 0.0
        return (self.has_update + self.no_update) / self.total * 100


class StatusRulePath(BaseModel):
    """Audit record of the rule path leading to a status decision.

    This is used for logging and debugging status computation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: Annotated[str, Field(min_length=1)]
    fetch_ok: bool
    parse_ok: bool
    items_emitted: int
    items_new: int
    items_updated: int
    all_dates_missing: bool
    has_stable_ordering: bool
    is_status_only: bool
    rule_expression: str
    computed_status: str
    computed_reason_code: str
