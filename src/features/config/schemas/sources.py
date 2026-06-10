"""Source configuration schema."""

from typing import Annotated

from pydantic import Field, field_validator, model_validator

from src.data_model import StrictBaseModel
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier


__all__ = [
    "SourceConfig",
    "SourcesConfig",
    "SourceKind",
    "SourceMethod",
    "SourceTier",
]


class SourceConfig(StrictBaseModel):
    """Configuration for a single source.

    Attributes:
        id: Unique identifier for the source.
        name: Human-readable name.
        url: Primary URL for the source.
        tier: Source tier (0, 1, or 2).
        method: Ingestion method.
        kind: Content kind classification.
        timezone: Timezone string for date parsing.
        max_items: Maximum items to fetch per run.
        enabled: Whether the source is enabled.
        headers: Optional custom headers for requests.
        query: Optional query string (for API sources).
    """

    id: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    url: Annotated[str, Field(min_length=1)]
    tier: SourceTier
    method: SourceMethod
    kind: SourceKind
    timezone: Annotated[str, Field(min_length=1, max_length=50)] = "UTC"
    max_items: Annotated[int, Field(ge=0, le=1000)] = 100
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    query: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL starts with http:// or https://."""
        if not v.startswith(("http://", "https://")):
            msg = "URL must start with http:// or https://"
            raise ValueError(msg)
        return v

    @field_validator("headers")
    @classmethod
    def validate_no_auth_headers(cls, v: dict[str, str]) -> dict[str, str]:
        """Ensure no Authorization headers are stored in config."""
        forbidden = {"authorization", "cookie", "x-api-key"}
        for key in v:
            if key.lower() in forbidden:
                msg = f"Header '{key}' must not be stored in config; use environment variables"
                raise ValueError(msg)
        return v


class SourcesConfig(StrictBaseModel):
    """Root configuration for sources.yaml.

    Attributes:
        version: Schema version.
        defaults: Default values for sources.
        sources: List of source configurations.
    """

    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")] = "1.0"
    defaults: dict[str, str | int | bool] = Field(default_factory=dict)
    sources: list[SourceConfig]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "SourcesConfig":
        """Ensure all source IDs are unique."""
        ids = [s.id for s in self.sources]
        duplicates = [id_ for id_ in ids if ids.count(id_) > 1]
        if duplicates:
            msg = f"Duplicate source IDs found: {set(duplicates)}"
            raise ValueError(msg)
        return self
