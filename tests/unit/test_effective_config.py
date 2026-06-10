"""Unit tests for EffectiveConfig."""

import json

import pytest
from pydantic import ValidationError

from src.features.config.effective import EffectiveConfig
from src.features.config.schemas.base import (
    LinkType,
    SourceKind,
    SourceMethod,
    SourceTier,
)
from src.features.config.schemas.entities import (
    EntitiesConfig,
    EntityConfig,
    EntityRegion,
)
from src.features.config.schemas.sources import SourceConfig, SourcesConfig
from src.features.config.schemas.topics import TopicConfig, TopicsConfig


@pytest.fixture
def sample_sources() -> SourcesConfig:
    """Create sample sources configuration."""
    return SourcesConfig(
        version="1.0",
        sources=[
            SourceConfig(
                id="source-1",
                name="Source 1",
                url="https://example.com/1",
                tier=SourceTier.TIER_0,
                method=SourceMethod.RSS_ATOM,
                kind=SourceKind.BLOG,
                enabled=True,
            ),
            SourceConfig(
                id="source-2",
                name="Source 2",
                url="https://example.com/2",
                tier=SourceTier.TIER_1,
                method=SourceMethod.HTML_LIST,
                kind=SourceKind.NEWS,
                enabled=False,
            ),
        ],
    )


@pytest.fixture
def sample_entities() -> EntitiesConfig:
    """Create sample entities configuration."""
    return EntitiesConfig(
        version="1.0",
        entities=[
            EntityConfig(
                id="entity-1",
                name="Entity 1",
                region=EntityRegion.INTL,
                keywords=["keyword1"],
                prefer_links=[LinkType.OFFICIAL],
            ),
            EntityConfig(
                id="entity-2",
                name="Entity 2",
                region=EntityRegion.CN,
                keywords=["keyword2"],
                prefer_links=[LinkType.GITHUB],
            ),
        ],
    )


@pytest.fixture
def sample_topics() -> TopicsConfig:
    """Create sample topics configuration."""
    return TopicsConfig(
        version="1.0",
        topics=[
            TopicConfig(name="Topic 1", keywords=["key1"]),
        ],
    )


@pytest.fixture
def effective_config(
    sample_sources: SourcesConfig,
    sample_entities: EntitiesConfig,
    sample_topics: TopicsConfig,
) -> EffectiveConfig:
    """Create sample effective configuration."""
    return EffectiveConfig(
        sources=sample_sources,
        entities=sample_entities,
        topics=sample_topics,
        file_checksums={
            "/path/sources.yaml": "abc123",
            "/path/entities.yaml": "def456",
            "/path/topics.yaml": "ghi789",
        },
        run_id="test-run-123",
    )


class TestEffectiveConfig:
    """Tests for EffectiveConfig."""

    @pytest.mark.unit
    def test_immutability(self, effective_config: EffectiveConfig) -> None:
        """Test that EffectiveConfig is frozen."""
        with pytest.raises(ValidationError):
            effective_config.run_id = "new-id"  # type: ignore[misc]

    @pytest.mark.unit
    def test_to_normalized_json_stable(self, effective_config: EffectiveConfig) -> None:
        """Test that normalized JSON is stable across calls."""
        json1 = effective_config.to_normalized_json()
        json2 = effective_config.to_normalized_json()
        assert json1 == json2

    @pytest.mark.unit
    def test_to_normalized_json_sorted_keys(
        self, effective_config: EffectiveConfig
    ) -> None:
        """Test that normalized JSON has sorted keys."""
        json_str = effective_config.to_normalized_json()
        data = json.loads(json_str)
        # Check top-level keys are sorted
        keys = list(data.keys())
        assert keys == sorted(keys)

    @pytest.mark.unit
    def test_to_normalized_dict(self, effective_config: EffectiveConfig) -> None:
        """Test to_normalized_dict returns correct structure."""
        data = effective_config.to_normalized_dict()
        assert "sources" in data
        assert "entities" in data
        assert "topics" in data
        assert "run_id" in data
        assert data["run_id"] == "test-run-123"

    @pytest.mark.unit
    def test_compute_checksum_stable(self, effective_config: EffectiveConfig) -> None:
        """Test that checksum is stable across calls."""
        checksum1 = effective_config.compute_checksum()
        checksum2 = effective_config.compute_checksum()
        assert checksum1 == checksum2
        assert len(checksum1) == 64  # SHA-256 hex length

    @pytest.mark.unit
    def test_compute_checksum_different_for_different_configs(
        self,
        sample_sources: SourcesConfig,
        sample_entities: EntitiesConfig,
        sample_topics: TopicsConfig,
    ) -> None:
        """Test that different configs have different checksums."""
        config1 = EffectiveConfig(
            sources=sample_sources,
            entities=sample_entities,
            topics=sample_topics,
            file_checksums={},
            run_id="run-1",
        )
        config2 = EffectiveConfig(
            sources=sample_sources,
            entities=sample_entities,
            topics=sample_topics,
            file_checksums={},
            run_id="run-2",
        )
        assert config1.compute_checksum() != config2.compute_checksum()

    @pytest.mark.unit
    def test_get_enabled_sources(self, effective_config: EffectiveConfig) -> None:
        """Test get_enabled_sources returns only enabled sources."""
        enabled = effective_config.get_enabled_sources()
        assert len(enabled) == 1
        assert enabled[0].id == "source-1"

    @pytest.mark.unit
    def test_get_entities_by_region(self, effective_config: EffectiveConfig) -> None:
        """Test get_entities_by_region filters correctly."""
        intl_entities = effective_config.get_entities_by_region("intl")
        cn_entities = effective_config.get_entities_by_region("cn")
        assert len(intl_entities) == 1
        assert len(cn_entities) == 1
        assert intl_entities[0].id == "entity-1"
        assert cn_entities[0].id == "entity-2"

    @pytest.mark.unit
    def test_summary(self, effective_config: EffectiveConfig) -> None:
        """Test summary returns correct information."""
        summary = effective_config.summary()
        assert summary["run_id"] == "test-run-123"
        assert summary["sources_count"] == 2
        assert summary["enabled_sources_count"] == 1
        assert summary["entities_count"] == 2
        assert summary["topics_count"] == 1
        assert "config_checksum" in summary
        assert len(summary["file_checksums"]) == 3  # type: ignore[arg-type]


class TestEffectiveConfigIdempotency:
    """Tests for EffectiveConfig idempotency requirements."""

    @pytest.mark.unit
    def test_repeated_normalization_identical(
        self,
        sample_sources: SourcesConfig,
        sample_entities: EntitiesConfig,
        sample_topics: TopicsConfig,
    ) -> None:
        """Test that repeated loads produce identical normalized objects."""
        config1 = EffectiveConfig(
            sources=sample_sources,
            entities=sample_entities,
            topics=sample_topics,
            file_checksums={},
            run_id="test-run",
        )
        config2 = EffectiveConfig(
            sources=sample_sources,
            entities=sample_entities,
            topics=sample_topics,
            file_checksums={},
            run_id="test-run",
        )

        # Byte-identical normalized JSON
        assert config1.to_normalized_json() == config2.to_normalized_json()

        # Identical checksums
        assert config1.compute_checksum() == config2.compute_checksum()
