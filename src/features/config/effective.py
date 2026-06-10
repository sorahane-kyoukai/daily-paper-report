"""Effective configuration combining all validated configs."""

import hashlib
import json
from typing import Annotated

from pydantic import Field

from src.data_model import StrictBaseModel
from src.features.config.schemas.entities import EntitiesConfig, EntityConfig
from src.features.config.schemas.sources import SourceConfig, SourcesConfig
from src.features.config.schemas.topics import TopicsConfig


class EffectiveConfig(StrictBaseModel):
    """Combined effective configuration for a run.

    This represents the immutable, normalized configuration that is
    used throughout a run. Once created, it cannot be modified.

    Attributes:
        sources: Validated sources configuration.
        entities: Validated entities configuration.
        topics: Validated topics configuration.
        file_checksums: SHA-256 checksums of source files.
        run_id: Unique identifier for the run.
    """

    sources: SourcesConfig
    entities: EntitiesConfig
    topics: TopicsConfig
    file_checksums: Annotated[dict[str, str], Field(default_factory=dict)]
    run_id: str

    def to_normalized_dict(self) -> dict[str, object]:
        """Convert to a normalized dictionary with stable key ordering.

        Returns:
            Dictionary representation with sorted keys at all levels.
        """
        result: dict[str, object] = json.loads(self.to_normalized_json())
        return result

    def to_normalized_json(self) -> str:
        """Convert to normalized JSON with stable ordering.

        This ensures idempotent serialization - repeated calls produce
        identical output.

        Returns:
            JSON string with sorted keys.
        """
        data = self.model_dump(mode="json")
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def compute_checksum(self) -> str:
        """Compute SHA-256 checksum of normalized configuration.

        Returns:
            Hex-encoded SHA-256 checksum.
        """
        normalized = self.to_normalized_json()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_source_by_id(self, source_id: str) -> SourceConfig | None:
        """Get a source configuration by ID.

        Args:
            source_id: The source ID to look up.

        Returns:
            SourceConfig if found, None otherwise.
        """
        for source in self.sources.sources:
            if source.id == source_id:
                return source
        return None

    def get_entity_by_id(self, entity_id: str) -> EntityConfig | None:
        """Get an entity configuration by ID.

        Args:
            entity_id: The entity ID to look up.

        Returns:
            EntityConfig if found, None otherwise.
        """
        for entity in self.entities.entities:
            if entity.id == entity_id:
                return entity
        return None

    def get_enabled_sources(self) -> list[SourceConfig]:
        """Get all enabled sources.

        Returns:
            List of enabled source configurations.
        """
        return [s for s in self.sources.sources if s.enabled]

    def get_entities_by_region(self, region: str) -> list[EntityConfig]:
        """Get entities by region.

        Args:
            region: Region to filter by ('cn' or 'intl').

        Returns:
            List of matching entity configurations.
        """
        return [e for e in self.entities.entities if e.region.value == region]

    def summary(self) -> dict[str, object]:
        """Get a summary of the effective configuration.

        Returns:
            Dictionary with summary information.
        """
        return {
            "run_id": self.run_id,
            "sources_count": len(self.sources.sources),
            "enabled_sources_count": len(self.get_enabled_sources()),
            "entities_count": len(self.entities.entities),
            "topics_count": len(self.topics.topics),
            "config_checksum": self.compute_checksum(),
            "file_checksums": self.file_checksums,
        }
