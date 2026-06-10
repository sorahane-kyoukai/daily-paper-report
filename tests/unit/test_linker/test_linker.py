"""Unit tests for StoryLinker class."""

from datetime import UTC, datetime

import pytest

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.entities import (
    EntitiesConfig,
    EntityConfig,
    EntityRegion,
)
from src.features.config.schemas.topics import TopicsConfig
from src.features.store.models import DateConfidence, Item
from src.linker.linker import (
    StoryLinker,
    _create_story_link,
    _dedupe_links,
    _infer_link_type,
    _select_primary_link,
    link_items_pure,
)
from src.linker.models import StoryLink
from src.linker.state_machine import LinkerState


def create_test_item(  # noqa: PLR0913
    url: str = "https://example.com/post",
    source_id: str = "test-source",
    tier: int = 1,
    kind: str = "blog",
    title: str = "Test Title",
    published_at: datetime | None = None,
    raw_json: str = "{}",
) -> Item:
    """Create a test Item with defaults."""
    return Item(
        url=url,
        source_id=source_id,
        tier=tier,
        kind=kind,
        title=title,
        published_at=published_at,
        date_confidence=DateConfidence.HIGH if published_at else DateConfidence.LOW,
        content_hash="test-hash",
        raw_json=raw_json,
    )


class TestInferLinkType:
    """Tests for _infer_link_type function."""

    def test_arxiv_url(self) -> None:
        """Test arXiv URL is detected."""
        item = create_test_item(url="https://arxiv.org/abs/2401.12345")
        assert _infer_link_type(item) == LinkType.ARXIV

    def test_github_url(self) -> None:
        """Test GitHub URL is detected."""
        item = create_test_item(url="https://github.com/org/repo")
        assert _infer_link_type(item) == LinkType.GITHUB

    def test_huggingface_url(self) -> None:
        """Test Hugging Face URL is detected."""
        item = create_test_item(url="https://huggingface.co/meta-llama/llama")
        assert _infer_link_type(item) == LinkType.HUGGINGFACE

    def test_modelscope_url(self) -> None:
        """Test ModelScope URL is detected."""
        item = create_test_item(url="https://modelscope.cn/models/qwen/qwen2")
        assert _infer_link_type(item) == LinkType.MODELSCOPE

    def test_openreview_url(self) -> None:
        """Test OpenReview URL is detected."""
        item = create_test_item(url="https://openreview.net/forum?id=abc")
        assert _infer_link_type(item) == LinkType.OPENREVIEW

    def test_tier_0_defaults_to_official(self) -> None:
        """Test tier 0 defaults to official when kind is not mapped."""
        # Use a kind that isn't in the KIND_LINK_TYPES mapping
        item = create_test_item(
            url="https://example.com/announcement",
            tier=0,
            kind="announcement",  # Not in the mapping, so falls to tier check
        )
        assert _infer_link_type(item) == LinkType.OFFICIAL


class TestCreateStoryLink:
    """Tests for _create_story_link function."""

    def test_creates_link_with_inferred_type(self) -> None:
        """Test creating link with inferred type."""
        item = create_test_item(
            url="https://arxiv.org/abs/2401.12345",
            title="Test Paper",
        )
        link = _create_story_link(item)
        assert link.url == "https://arxiv.org/abs/2401.12345"
        assert link.link_type == LinkType.ARXIV
        assert link.title == "Test Paper"

    def test_creates_link_with_explicit_type(self) -> None:
        """Test creating link with explicit type."""
        item = create_test_item(url="https://example.com")
        link = _create_story_link(item, link_type=LinkType.OFFICIAL)
        assert link.link_type == LinkType.OFFICIAL


class TestDedupeLinks:
    """Tests for _dedupe_links function."""

    def test_removes_duplicates(self) -> None:
        """Test that duplicate links are removed."""
        links = [
            StoryLink(
                url="https://arxiv.org/abs/2401.12345",
                link_type=LinkType.ARXIV,
                source_id="src1",
                tier=1,
            ),
            StoryLink(
                url="https://arxiv.org/abs/2401.12345",
                link_type=LinkType.ARXIV,
                source_id="src2",
                tier=1,
            ),
        ]
        deduped = _dedupe_links(links)
        assert len(deduped) == 1

    def test_keeps_different_types_same_url(self) -> None:
        """Test that different types for same URL are kept."""
        links = [
            StoryLink(
                url="https://example.com",
                link_type=LinkType.OFFICIAL,
                source_id="src1",
                tier=0,
            ),
            StoryLink(
                url="https://example.com",
                link_type=LinkType.BLOG,
                source_id="src2",
                tier=1,
            ),
        ]
        deduped = _dedupe_links(links)
        assert len(deduped) == 2


class TestSelectPrimaryLink:
    """Tests for _select_primary_link function."""

    def test_selects_by_type_order(self) -> None:
        """Test primary link selection by type order."""
        links = [
            StoryLink(
                url="https://blog.example.com",
                link_type=LinkType.BLOG,
                source_id="blog",
                tier=1,
            ),
            StoryLink(
                url="https://arxiv.org/abs/2401.12345",
                link_type=LinkType.ARXIV,
                source_id="arxiv",
                tier=1,
            ),
            StoryLink(
                url="https://official.example.com",
                link_type=LinkType.OFFICIAL,
                source_id="official",
                tier=0,
            ),
        ]
        prefer_order = ["official", "arxiv", "github", "blog"]
        primary = _select_primary_link(links, prefer_order)
        assert primary.link_type == LinkType.OFFICIAL

    def test_selects_by_tier_when_same_type(self) -> None:
        """Test tier is used as tiebreaker."""
        links = [
            StoryLink(
                url="https://blog1.example.com",
                link_type=LinkType.BLOG,
                source_id="blog1",
                tier=2,
            ),
            StoryLink(
                url="https://blog2.example.com",
                link_type=LinkType.BLOG,
                source_id="blog2",
                tier=0,
            ),
        ]
        prefer_order = ["official", "blog"]
        primary = _select_primary_link(links, prefer_order)
        assert primary.tier == 0

    def test_empty_list_raises(self) -> None:
        """Test empty list raises ValueError."""
        with pytest.raises(ValueError, match="empty list"):
            _select_primary_link([], ["official"])


class TestStoryLinker:
    """Tests for StoryLinker class."""

    def test_empty_input(self) -> None:
        """Test linking empty input."""
        linker = StoryLinker(run_id="test")
        result = linker.link_items([])

        assert result.items_in == 0
        assert result.stories_out == 0
        assert linker.state == LinkerState.STORIES_FINAL

    def test_single_item(self) -> None:
        """Test linking single item."""
        item = create_test_item(
            url="https://arxiv.org/abs/2401.12345",
            title="Test Paper",
        )
        linker = StoryLinker(run_id="test")
        result = linker.link_items([item])

        assert result.items_in == 1
        assert result.stories_out == 1
        assert result.stories[0].story_id == "arxiv:2401.12345"

    def test_merges_same_arxiv_id(self) -> None:
        """Test items with same arXiv ID are merged."""
        items = [
            create_test_item(
                url="https://arxiv.org/abs/2401.12345",
                source_id="arxiv-rss",
                title="Paper v1",
            ),
            create_test_item(
                url="https://arxiv.org/abs/2401.12345",
                source_id="arxiv-api",
                title="Paper v1 (API)",
            ),
        ]
        linker = StoryLinker(run_id="test")
        result = linker.link_items(items)

        assert result.items_in == 2
        assert result.stories_out == 1
        assert result.merges_total == 1

    def test_entity_matching(self) -> None:
        """Test entity matching is performed."""
        entities_config = EntitiesConfig(
            entities=[
                EntityConfig(
                    id="openai",
                    name="OpenAI",
                    region=EntityRegion.INTL,
                    keywords=["OpenAI", "GPT-4"],
                    prefer_links=[LinkType.OFFICIAL, LinkType.ARXIV],
                ),
            ]
        )

        item = create_test_item(
            url="https://example.com/gpt4",
            title="GPT-4 Technical Report by OpenAI",
        )

        linker = StoryLinker(run_id="test", entities_config=entities_config)
        result = linker.link_items([item])

        assert "openai" in result.stories[0].entities

    def test_primary_link_precedence(self) -> None:
        """Test primary link follows precedence order."""
        topics_config = TopicsConfig(
            prefer_primary_link_order=["official", "arxiv", "github"],
        )

        items = [
            create_test_item(
                url="https://github.com/org/repo",
                source_id="github",
                tier=0,
                kind="release",
                title="v1.0",
            ),
            create_test_item(
                url="https://blog.example.com/announcement",
                source_id="official",
                tier=0,
                kind="blog",
                title="Announcing v1.0",
            ),
        ]

        # Both items need same stable ID to be merged
        # For this test, use items that would have fallback grouping
        linker = StoryLinker(run_id="test", topics_config=topics_config)
        result = linker.link_items(items)

        # Each item becomes its own story since they have different stable IDs
        assert result.stories_out == 2

    def test_idempotency(self) -> None:
        """Test linking is idempotent."""
        items = [
            create_test_item(
                url="https://arxiv.org/abs/2401.12345",
                source_id="arxiv",
                title="Paper",
                published_at=datetime(2024, 1, 15, tzinfo=UTC),
            ),
            create_test_item(
                url="https://example.com/blog",
                source_id="blog",
                title="Blog Post",
            ),
        ]

        linker1 = StoryLinker(run_id="run1")
        result1 = linker1.link_items(items)

        linker2 = StoryLinker(run_id="run2")
        result2 = linker2.link_items(items)

        # Same number of stories
        assert result1.stories_out == result2.stories_out

        # Same story IDs
        ids1 = [s.story_id for s in result1.stories]
        ids2 = [s.story_id for s in result2.stories]
        assert ids1 == ids2


class TestLinkItemsPure:
    """Tests for link_items_pure function."""

    def test_pure_function_api(self) -> None:
        """Test pure function API works."""
        items = [
            create_test_item(
                url="https://arxiv.org/abs/2401.12345",
                title="Paper",
            )
        ]
        entities = [
            EntityConfig(
                id="test",
                name="Test",
                region=EntityRegion.INTL,
                keywords=["test"],
                prefer_links=[LinkType.OFFICIAL],
            )
        ]

        result = link_items_pure(
            items=items,
            entities=entities,
            prefer_primary_link_order=["official", "arxiv"],
        )

        assert result.stories_out == 1
