"""Unit tests for entity matcher."""

import json

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.entities import EntityConfig, EntityRegion, EntityType
from src.features.store.models import DateConfidence, Item
from src.linker.entity_matcher import (
    _build_search_text,
    get_all_entity_ids,
    get_primary_entity,
    match_item_to_entities,
)


def create_test_item(
    title: str = "Test Title",
    raw_json: str = "{}",
) -> Item:
    """Create a test Item."""
    return Item(
        url="https://example.com/post",
        source_id="test-source",
        tier=1,
        kind="blog",
        title=title,
        content_hash="test-hash",
        raw_json=raw_json,
        date_confidence=DateConfidence.LOW,
    )


def create_test_entity(
    entity_id: str = "test-entity",
    name: str = "Test Entity",
    keywords: list[str] | None = None,
    aliases: list[str] | None = None,
) -> EntityConfig:
    """Create a test EntityConfig."""
    return EntityConfig(
        id=entity_id,
        name=name,
        region=EntityRegion.INTL,
        keywords=keywords or ["test"],
        prefer_links=[LinkType.OFFICIAL],
        aliases=aliases or [],
    )


class TestMatchItemToEntities:
    """Tests for match_item_to_entities function."""

    def test_no_match(self) -> None:
        """Test item with no matching keywords."""
        item = create_test_item(title="Random blog post")
        entities = [create_test_entity(keywords=["OpenAI", "GPT"])]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 0

    def test_single_keyword_match(self) -> None:
        """Test matching single keyword in title."""
        item = create_test_item(title="OpenAI announces new model")
        entities = [create_test_entity(entity_id="openai", keywords=["OpenAI"])]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1
        assert matches[0].entity_id == "openai"
        assert "OpenAI" in matches[0].matched_keywords

    def test_multiple_keyword_match(self) -> None:
        """Test matching multiple keywords."""
        item = create_test_item(title="OpenAI GPT-4 Technical Report")
        entities = [
            create_test_entity(entity_id="openai", keywords=["OpenAI", "GPT-4", "GPT"])
        ]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1
        assert len(matches[0].matched_keywords) >= 2

    def test_multiple_entities_match(self) -> None:
        """Test matching multiple entities."""
        item = create_test_item(title="OpenAI and Anthropic release new models")
        entities = [
            create_test_entity(entity_id="openai", keywords=["OpenAI"]),
            create_test_entity(entity_id="anthropic", keywords=["Anthropic"]),
        ]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 2

    def test_alias_match(self) -> None:
        """Test matching via alias."""
        item = create_test_item(title="Google DeepMind paper")
        entities = [
            create_test_entity(
                entity_id="deepmind",
                keywords=["DeepMind"],
                aliases=["Google DeepMind"],
            )
        ]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1
        assert "Google DeepMind" in matches[0].matched_keywords

    def test_case_insensitive_match(self) -> None:
        """Test matching is case insensitive."""
        item = create_test_item(title="OPENAI announces CLAUDE competitor")
        entities = [create_test_entity(entity_id="openai", keywords=["openai"])]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1

    def test_raw_json_abstract_match(self) -> None:
        """Test matching in raw_json abstract."""
        raw = json.dumps({"abstract": "This paper from OpenAI discusses..."})
        item = create_test_item(title="Technical Report", raw_json=raw)
        entities = [create_test_entity(entity_id="openai", keywords=["OpenAI"])]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1

    def test_sorted_by_score(self) -> None:
        """Test matches are sorted by score descending."""
        item = create_test_item(title="OpenAI GPT-4 paper mentions Anthropic")
        entities = [
            create_test_entity(entity_id="openai", keywords=["OpenAI", "GPT-4"]),
            create_test_entity(entity_id="anthropic", keywords=["Anthropic"]),
        ]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 2
        # OpenAI should have higher score (more matches)
        assert matches[0].entity_id == "openai"

    def test_word_boundary_matching(self) -> None:
        """Test word boundary matching prevents partial matches."""
        item = create_test_item(title="AI safety research")
        entities = [create_test_entity(entity_id="openai", keywords=["OpenAI"])]

        # "AI" should not match "OpenAI"
        matches = match_item_to_entities(item, entities)
        assert len(matches) == 0


class TestGetPrimaryEntity:
    """Tests for get_primary_entity function."""

    def test_returns_first_entity(self) -> None:
        """Test returns first entity ID."""
        item = create_test_item(title="OpenAI paper")
        entities = [create_test_entity(entity_id="openai", keywords=["OpenAI"])]
        matches = match_item_to_entities(item, entities)

        primary = get_primary_entity(matches)
        assert primary == "openai"

    def test_returns_none_for_empty(self) -> None:
        """Test returns None for empty matches."""
        primary = get_primary_entity([])
        assert primary is None


class TestGetAllEntityIds:
    """Tests for get_all_entity_ids function."""

    def test_returns_all_ids(self) -> None:
        """Test returns all entity IDs."""
        item = create_test_item(title="OpenAI and Anthropic collaboration")
        entities = [
            create_test_entity(entity_id="openai", keywords=["OpenAI"]),
            create_test_entity(entity_id="anthropic", keywords=["Anthropic"]),
        ]
        matches = match_item_to_entities(item, entities)

        ids = get_all_entity_ids(matches)
        assert "openai" in ids
        assert "anthropic" in ids

    def test_returns_empty_for_no_matches(self) -> None:
        """Test returns empty list for no matches."""
        ids = get_all_entity_ids([])
        assert ids == []


class TestBuildSearchText:
    """Tests for _build_search_text function with author matching."""

    def test_includes_title(self) -> None:
        """Test search text includes title."""
        item = create_test_item(title="Test Paper Title")
        search_text = _build_search_text(item)
        assert "test paper title" in search_text

    def test_includes_abstract(self) -> None:
        """Test search text includes abstract from raw_json."""
        raw = json.dumps({"abstract": "This is the abstract"})
        item = create_test_item(title="Title", raw_json=raw)
        search_text = _build_search_text(item)
        assert "this is the abstract" in search_text

    def test_includes_authors_list(self) -> None:
        """Test search text includes authors as list."""
        raw = json.dumps({"authors": ["Ilya Sutskever", "Geoffrey Hinton"]})
        item = create_test_item(title="Paper Title", raw_json=raw)
        search_text = _build_search_text(item)
        assert "ilya sutskever" in search_text
        assert "geoffrey hinton" in search_text

    def test_includes_authors_string(self) -> None:
        """Test search text includes authors as string."""
        raw = json.dumps({"authors": "John Doe, Jane Smith"})
        item = create_test_item(title="Paper Title", raw_json=raw)
        search_text = _build_search_text(item)
        assert "john doe" in search_text
        assert "jane smith" in search_text

    def test_handles_empty_raw_json(self) -> None:
        """Test handles empty raw_json."""
        item = create_test_item(title="Title", raw_json="{}")
        search_text = _build_search_text(item)
        assert "title" in search_text

    def test_handles_invalid_json(self) -> None:
        """Test handles invalid JSON gracefully."""
        item = create_test_item(title="Title", raw_json="not json")
        search_text = _build_search_text(item)
        assert "title" in search_text


class TestAuthorBasedEntityMatching:
    """Tests for entity matching based on authors."""

    def test_match_researcher_by_name(self) -> None:
        """Test matching researcher entity by author name."""
        raw = json.dumps({"authors": ["Ilya Sutskever", "John Doe"]})
        item = create_test_item(title="Attention Is All You Need", raw_json=raw)
        entities = [
            EntityConfig(
                id="ilya-sutskever",
                name="Ilya Sutskever",
                region=EntityRegion.INTL,
                entity_type=EntityType.RESEARCHER,
                keywords=["Ilya Sutskever", "Sutskever"],
                prefer_links=[LinkType.ARXIV],
            )
        ]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1
        assert matches[0].entity_id == "ilya-sutskever"

    def test_match_institution_by_affiliation(self) -> None:
        """Test matching institution by affiliation keyword."""
        raw = json.dumps(
            {"abstract": "Researchers at Google Research present a new model..."}
        )
        item = create_test_item(title="New Research Paper", raw_json=raw)
        entities = [
            EntityConfig(
                id="google-research",
                name="Google Research",
                region=EntityRegion.INTL,
                entity_type=EntityType.INSTITUTION,
                keywords=["Google Research", "Google Brain"],
                prefer_links=[LinkType.OFFICIAL],
            )
        ]

        matches = match_item_to_entities(item, entities)
        assert len(matches) == 1
        assert matches[0].entity_id == "google-research"

    def test_combined_author_and_title_boost(self) -> None:
        """Test that matching in both author and title gives higher score."""
        raw = json.dumps({"authors": ["Hinton"]})
        item_author_only = create_test_item(title="A New Paper", raw_json=raw)

        item_both = create_test_item(
            title="Hinton's New Paper",
            raw_json=json.dumps({"authors": ["Hinton"]}),
        )

        entities = [
            EntityConfig(
                id="geoffrey-hinton",
                name="Geoffrey Hinton",
                region=EntityRegion.INTL,
                entity_type=EntityType.RESEARCHER,
                keywords=["Hinton"],
                prefer_links=[LinkType.ARXIV],
            )
        ]

        matches_author_only = match_item_to_entities(item_author_only, entities)
        matches_both = match_item_to_entities(item_both, entities)

        assert len(matches_author_only) == 1
        assert len(matches_both) == 1
        # Title boost should give higher score
        assert matches_both[0].match_score > matches_author_only[0].match_score
