"""Entity configuration schema."""

from enum import Enum
from typing import Annotated

from pydantic import Field, model_validator

from src.data_model import StrictBaseModel
from src.features.config.schemas.base import LinkType


class EntityRegion(str, Enum):
    """Entity region classification."""

    CN = "cn"
    INTL = "intl"


class EntityType(str, Enum):
    """Entity type classification for quality filtering.

    Used to distinguish between organizations (companies/labs),
    individual researchers, and academic institutions.
    """

    ORGANIZATION = "organization"
    RESEARCHER = "researcher"
    INSTITUTION = "institution"


class EntityConfig(StrictBaseModel):
    """Configuration for a single entity.

    Attributes:
        id: Unique identifier for the entity.
        name: Human-readable name.
        region: Region classification (cn or intl).
        entity_type: Type classification (organization, researcher, institution).
        keywords: Keywords for matching (non-empty).
        prefer_links: Preferred link types for primary link selection.
        aliases: Alternative names for the entity.
    """

    id: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    region: EntityRegion
    entity_type: EntityType = EntityType.ORGANIZATION
    keywords: Annotated[list[str], Field(min_length=1)]
    prefer_links: Annotated[list[LinkType], Field(min_length=1)]
    aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_keywords_non_empty(self) -> "EntityConfig":
        """Ensure keywords list contains non-empty strings."""
        for keyword in self.keywords:
            if not keyword.strip():
                msg = "Keywords must be non-empty strings"
                raise ValueError(msg)
        return self


class EntitiesConfig(StrictBaseModel):
    """Root configuration for entities.yaml.

    Attributes:
        version: Schema version.
        entities: List of entity configurations.
    """

    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")] = "1.0"
    entities: list[EntityConfig]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "EntitiesConfig":
        """Ensure all entity IDs are unique."""
        ids = [e.id for e in self.entities]
        duplicates = [id_ for id_ in ids if ids.count(id_) > 1]
        if duplicates:
            msg = f"Duplicate entity IDs found: {set(duplicates)}"
            raise ValueError(msg)
        return self
