"""Unit tests for configuration schemas."""

import pytest
from pydantic import ValidationError

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
from src.features.config.schemas.topics import (
    DedupeConfig,
    QuotasConfig,
    ScoringConfig,
    TopicConfig,
    TopicsConfig,
)


class TestSourceConfig:
    """Tests for SourceConfig schema."""

    @pytest.mark.unit
    def test_valid_source_config(self) -> None:
        """Test creating a valid source configuration."""
        config = SourceConfig(
            id="test-source",
            name="Test Source",
            url="https://example.com/feed.xml",
            tier=SourceTier.TIER_0,
            method=SourceMethod.RSS_ATOM,
            kind=SourceKind.BLOG,
        )
        assert config.id == "test-source"
        assert config.name == "Test Source"
        assert config.tier == SourceTier.TIER_0
        assert config.timezone == "UTC"
        assert config.max_items == 100
        assert config.enabled is True

    @pytest.mark.unit
    def test_source_config_with_all_fields(self) -> None:
        """Test source config with all optional fields."""
        config = SourceConfig(
            id="full-source",
            name="Full Source",
            url="https://example.com/api",
            tier=SourceTier.TIER_1,
            method=SourceMethod.ARXIV_API,
            kind=SourceKind.PAPER,
            timezone="America/New_York",
            max_items=50,
            enabled=False,
            headers={"User-Agent": "TestBot/1.0"},
            query="search_query=all:electron",
        )
        assert config.timezone == "America/New_York"
        assert config.max_items == 50
        assert config.enabled is False
        assert config.headers == {"User-Agent": "TestBot/1.0"}
        assert config.query == "search_query=all:electron"

    @pytest.mark.unit
    def test_source_config_invalid_url(self) -> None:
        """Test that invalid URL raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig(
                id="bad-url",
                name="Bad URL Source",
                url="ftp://example.com/feed",
                tier=SourceTier.TIER_0,
                method=SourceMethod.RSS_ATOM,
                kind=SourceKind.BLOG,
            )
        errors = exc_info.value.errors()
        assert any("URL must start with http" in str(e["msg"]) for e in errors)

    @pytest.mark.unit
    def test_source_config_invalid_id_format(self) -> None:
        """Test that invalid ID format raises validation error."""
        with pytest.raises(ValidationError):
            SourceConfig(
                id="Invalid ID With Spaces",
                name="Test",
                url="https://example.com/feed",
                tier=SourceTier.TIER_0,
                method=SourceMethod.RSS_ATOM,
                kind=SourceKind.BLOG,
            )

    @pytest.mark.unit
    def test_source_config_negative_max_items(self) -> None:
        """Test that negative max_items raises validation error."""
        with pytest.raises(ValidationError):
            SourceConfig(
                id="test",
                name="Test",
                url="https://example.com/feed",
                tier=SourceTier.TIER_0,
                method=SourceMethod.RSS_ATOM,
                kind=SourceKind.BLOG,
                max_items=-1,
            )

    @pytest.mark.unit
    def test_source_config_auth_header_forbidden(self) -> None:
        """Test that Authorization header raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig(
                id="test",
                name="Test",
                url="https://example.com/feed",
                tier=SourceTier.TIER_0,
                method=SourceMethod.RSS_ATOM,
                kind=SourceKind.BLOG,
                headers={"Authorization": "Bearer secret"},
            )
        errors = exc_info.value.errors()
        assert any("must not be stored in config" in str(e["msg"]) for e in errors)


class TestSourcesConfig:
    """Tests for SourcesConfig (root) schema."""

    @pytest.mark.unit
    def test_valid_sources_config(self) -> None:
        """Test creating a valid sources configuration."""
        config = SourcesConfig(
            version="1.0",
            sources=[
                SourceConfig(
                    id="source-1",
                    name="Source 1",
                    url="https://example.com/1",
                    tier=SourceTier.TIER_0,
                    method=SourceMethod.RSS_ATOM,
                    kind=SourceKind.BLOG,
                ),
                SourceConfig(
                    id="source-2",
                    name="Source 2",
                    url="https://example.com/2",
                    tier=SourceTier.TIER_1,
                    method=SourceMethod.HTML_LIST,
                    kind=SourceKind.NEWS,
                ),
            ],
        )
        assert len(config.sources) == 2

    @pytest.mark.unit
    def test_sources_config_duplicate_ids(self) -> None:
        """Test that duplicate source IDs raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            SourcesConfig(
                sources=[
                    SourceConfig(
                        id="same-id",
                        name="Source 1",
                        url="https://example.com/1",
                        tier=SourceTier.TIER_0,
                        method=SourceMethod.RSS_ATOM,
                        kind=SourceKind.BLOG,
                    ),
                    SourceConfig(
                        id="same-id",
                        name="Source 2",
                        url="https://example.com/2",
                        tier=SourceTier.TIER_1,
                        method=SourceMethod.RSS_ATOM,
                        kind=SourceKind.BLOG,
                    ),
                ],
            )
        errors = exc_info.value.errors()
        assert any("Duplicate source IDs" in str(e["msg"]) for e in errors)


class TestEntityConfig:
    """Tests for EntityConfig schema."""

    @pytest.mark.unit
    def test_valid_entity_config(self) -> None:
        """Test creating a valid entity configuration."""
        config = EntityConfig(
            id="test-entity",
            name="Test Entity",
            region=EntityRegion.INTL,
            keywords=["keyword1", "keyword2"],
            prefer_links=[LinkType.OFFICIAL, LinkType.ARXIV],
        )
        assert config.id == "test-entity"
        assert config.region == EntityRegion.INTL
        assert len(config.keywords) == 2
        assert len(config.prefer_links) == 2

    @pytest.mark.unit
    def test_entity_config_cn_region(self) -> None:
        """Test entity with CN region."""
        config = EntityConfig(
            id="cn-entity",
            name="CN Entity",
            region=EntityRegion.CN,
            keywords=["keyword"],
            prefer_links=[LinkType.HUGGINGFACE],
        )
        assert config.region == EntityRegion.CN

    @pytest.mark.unit
    def test_entity_config_empty_keywords(self) -> None:
        """Test that empty keywords raises validation error."""
        with pytest.raises(ValidationError):
            EntityConfig(
                id="test",
                name="Test",
                region=EntityRegion.INTL,
                keywords=[],
                prefer_links=[LinkType.OFFICIAL],
            )

    @pytest.mark.unit
    def test_entity_config_empty_prefer_links(self) -> None:
        """Test that empty prefer_links raises validation error."""
        with pytest.raises(ValidationError):
            EntityConfig(
                id="test",
                name="Test",
                region=EntityRegion.INTL,
                keywords=["keyword"],
                prefer_links=[],
            )

    @pytest.mark.unit
    def test_entity_config_whitespace_keyword(self) -> None:
        """Test that whitespace-only keyword raises validation error."""
        with pytest.raises(ValidationError):
            EntityConfig(
                id="test",
                name="Test",
                region=EntityRegion.INTL,
                keywords=["  "],
                prefer_links=[LinkType.OFFICIAL],
            )


class TestEntitiesConfig:
    """Tests for EntitiesConfig (root) schema."""

    @pytest.mark.unit
    def test_valid_entities_config(self) -> None:
        """Test creating a valid entities configuration."""
        config = EntitiesConfig(
            version="1.0",
            entities=[
                EntityConfig(
                    id="entity-1",
                    name="Entity 1",
                    region=EntityRegion.INTL,
                    keywords=["key1"],
                    prefer_links=[LinkType.OFFICIAL],
                ),
                EntityConfig(
                    id="entity-2",
                    name="Entity 2",
                    region=EntityRegion.CN,
                    keywords=["key2"],
                    prefer_links=[LinkType.GITHUB],
                ),
            ],
        )
        assert len(config.entities) == 2

    @pytest.mark.unit
    def test_entities_config_duplicate_ids(self) -> None:
        """Test that duplicate entity IDs raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            EntitiesConfig(
                entities=[
                    EntityConfig(
                        id="same-id",
                        name="Entity 1",
                        region=EntityRegion.INTL,
                        keywords=["key1"],
                        prefer_links=[LinkType.OFFICIAL],
                    ),
                    EntityConfig(
                        id="same-id",
                        name="Entity 2",
                        region=EntityRegion.CN,
                        keywords=["key2"],
                        prefer_links=[LinkType.GITHUB],
                    ),
                ],
            )
        errors = exc_info.value.errors()
        assert any("Duplicate entity IDs" in str(e["msg"]) for e in errors)


class TestTopicConfig:
    """Tests for TopicConfig schema."""

    @pytest.mark.unit
    def test_valid_topic_config(self) -> None:
        """Test creating a valid topic configuration."""
        config = TopicConfig(
            name="Test Topic",
            keywords=["keyword1", "keyword2"],
            boost_weight=1.5,
        )
        assert config.name == "Test Topic"
        assert len(config.keywords) == 2
        assert config.boost_weight == 1.5

    @pytest.mark.unit
    def test_topic_config_default_boost(self) -> None:
        """Test topic config with default boost weight."""
        config = TopicConfig(
            name="Topic",
            keywords=["keyword"],
        )
        assert config.boost_weight == 1.0

    @pytest.mark.unit
    def test_topic_config_empty_keywords(self) -> None:
        """Test that empty keywords raises validation error."""
        with pytest.raises(ValidationError):
            TopicConfig(name="Topic", keywords=[])

    @pytest.mark.unit
    def test_topic_config_weight_out_of_range(self) -> None:
        """Test that weight > 5.0 raises validation error."""
        with pytest.raises(ValidationError):
            TopicConfig(
                name="Topic",
                keywords=["keyword"],
                boost_weight=6.0,
            )

    @pytest.mark.unit
    def test_topic_config_negative_weight(self) -> None:
        """Test that negative weight raises validation error."""
        with pytest.raises(ValidationError):
            TopicConfig(
                name="Topic",
                keywords=["keyword"],
                boost_weight=-0.5,
            )


class TestScoringConfig:
    """Tests for ScoringConfig schema."""

    @pytest.mark.unit
    def test_default_scoring_config(self) -> None:
        """Test default scoring configuration."""
        config = ScoringConfig()
        assert config.tier_0_weight == 3.0
        assert config.tier_1_weight == 2.0
        assert config.tier_2_weight == 1.0
        assert config.topic_match_weight == 1.5
        assert config.entity_match_weight == 2.0
        assert config.recency_decay_factor == 0.1

    @pytest.mark.unit
    def test_custom_scoring_config(self) -> None:
        """Test custom scoring configuration."""
        config = ScoringConfig(
            tier_0_weight=4.0,
            tier_1_weight=3.0,
            tier_2_weight=2.0,
            topic_match_weight=2.0,
            entity_match_weight=3.0,
            recency_decay_factor=0.2,
        )
        assert config.tier_0_weight == 4.0

    @pytest.mark.unit
    def test_scoring_config_weight_out_of_range(self) -> None:
        """Test that weight > 5.0 raises validation error."""
        with pytest.raises(ValidationError):
            ScoringConfig(tier_0_weight=6.0)


class TestDedupeConfig:
    """Tests for DedupeConfig schema."""

    @pytest.mark.unit
    def test_default_dedupe_config(self) -> None:
        """Test default deduplication configuration."""
        config = DedupeConfig()
        assert config.canonical_url_strip_params == []

    @pytest.mark.unit
    def test_dedupe_config_with_params(self) -> None:
        """Test deduplication config with params to strip."""
        config = DedupeConfig(
            canonical_url_strip_params=["utm_source", "utm_medium", "ref"]
        )
        assert len(config.canonical_url_strip_params) == 3


class TestQuotasConfig:
    """Tests for QuotasConfig schema."""

    @pytest.mark.unit
    def test_default_quotas_config(self) -> None:
        """Test default quotas configuration."""
        config = QuotasConfig()
        assert config.top5_max == 5
        assert config.radar_max == 10
        assert config.per_source_max == 10
        assert config.arxiv_per_category_max == 10
        assert "medical" in config.paper_exclusion_keywords

    @pytest.mark.unit
    def test_blank_paper_exclusion_keyword_rejected(self) -> None:
        """Blank paper exclusion keywords should fail validation."""
        with pytest.raises(ValidationError):
            QuotasConfig(paper_exclusion_keywords=["medical", ""])

    @pytest.mark.unit
    def test_negative_quota(self) -> None:
        """Test that negative quota raises validation error."""
        with pytest.raises(ValidationError):
            QuotasConfig(top5_max=-1)


class TestTopicsConfig:
    """Tests for TopicsConfig (root) schema."""

    @pytest.mark.unit
    def test_valid_topics_config(self) -> None:
        """Test creating a valid topics configuration."""
        config = TopicsConfig(
            version="1.0",
            dedupe=DedupeConfig(canonical_url_strip_params=["utm_source"]),
            scoring=ScoringConfig(tier_0_weight=4.0),
            quotas=QuotasConfig(top5_max=10),
            topics=[
                TopicConfig(name="Topic 1", keywords=["key1"]),
                TopicConfig(name="Topic 2", keywords=["key2"]),
            ],
            prefer_primary_link_order=[LinkType.OFFICIAL, LinkType.ARXIV],
        )
        assert len(config.topics) == 2
        assert len(config.prefer_primary_link_order) == 2

    @pytest.mark.unit
    def test_topics_config_defaults(self) -> None:
        """Test topics config with all defaults."""
        config = TopicsConfig()
        assert config.version == "1.0"
        assert config.dedupe.canonical_url_strip_params == []
        assert config.scoring.tier_0_weight == 3.0
        assert config.quotas.top5_max == 5
        assert config.topics == []
