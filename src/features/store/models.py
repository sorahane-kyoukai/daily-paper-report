"""Data models for the SQLite state store."""

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DateConfidence(str, Enum):
    """Confidence level for published_at dates.

    - high: Date from reliable source (RSS pubDate, API timestamp)
    - medium: Date inferred or with minor uncertainty
    - low: Date missing or highly uncertain
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ItemEventType(str, Enum):
    """Event type for item upsert operations.

    - NEW: Item was newly created
    - UPDATED: Item existed but content_hash changed
    - UNCHANGED: Item existed with same content_hash
    """

    NEW = "NEW"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"


class Item(BaseModel):
    """Stored item from a source.

    Represents a single piece of content (article, release, paper, etc.)
    with canonicalized URL as primary key.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: Annotated[str, Field(min_length=1, description="Canonical URL (primary key)")]
    source_id: Annotated[str, Field(min_length=1, description="Source identifier")]
    tier: Annotated[int, Field(ge=0, le=2, description="Source tier (0, 1, 2)")]
    kind: Annotated[str, Field(min_length=1, description="Content kind")]
    title: Annotated[str, Field(min_length=1, description="Item title")]
    published_at: datetime | None = Field(
        default=None, description="Publication timestamp (nullable)"
    )
    date_confidence: DateConfidence = Field(
        default=DateConfidence.LOW, description="Confidence in published_at"
    )
    content_hash: Annotated[
        str, Field(min_length=1, description="Hash of normalized content")
    ]
    raw_json: Annotated[str, Field(description="Raw JSON metadata (no secrets)")]
    first_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When item was first ingested",
    )
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When item was last seen",
    )

    @field_validator("date_confidence", mode="before")
    @classmethod
    def coerce_date_confidence(cls, v: Any) -> DateConfidence:
        """Coerce string to DateConfidence enum."""
        if isinstance(v, DateConfidence):
            return v
        if isinstance(v, str):
            return DateConfidence(v.lower())
        msg = f"Invalid date_confidence: {v}"
        raise ValueError(msg)


class Run(BaseModel):
    """Run tracking record.

    Tracks the lifecycle of a pipeline run from start to finish.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: Annotated[str, Field(min_length=1, description="Unique run identifier")]
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When run started",
    )
    finished_at: datetime | None = Field(
        default=None, description="When run finished (nullable if in progress)"
    )
    success: bool | None = Field(
        default=None, description="Whether run succeeded (nullable if in progress)"
    )
    error_summary: str | None = Field(
        default=None, description="Error summary if failed"
    )


class HttpCacheEntry(BaseModel):
    """HTTP cache entry for conditional requests.

    Stores ETag and Last-Modified headers for a source.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: Annotated[str, Field(min_length=1, description="Source identifier")]
    etag: str | None = Field(default=None, description="ETag header value")
    last_modified: str | None = Field(
        default=None, description="Last-Modified header value"
    )
    last_status: int | None = Field(default=None, description="Last HTTP status code")
    last_fetch_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When last fetched",
    )


class UpsertResult(BaseModel):
    """Result of an item upsert operation.

    Provides information about what happened during the upsert.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: ItemEventType = Field(description="What happened during upsert")
    affected_rows: int = Field(ge=0, description="Number of rows affected")
    item: Item = Field(description="The upserted item")
