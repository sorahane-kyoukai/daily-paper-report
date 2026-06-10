"""Integration tests for Story linker."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.entities import (
    EntitiesConfig,
    EntityConfig,
    EntityRegion,
)
from src.features.config.schemas.topics import TopicsConfig
from src.features.store.models import DateConfidence, Item
from src.linker.linker import StoryLinker
from src.linker.persistence import LinkerPersistence, write_daily_json
from src.linker.state_machine import LinkerState


def create_arxiv_item(
    arxiv_id: str,
    source_id: str = "arxiv-rss",
    title: str = "Test Paper",
    tier: int = 1,
) -> Item:
    """Create an arXiv item for testing."""
    return Item(
        url=f"https://arxiv.org/abs/{arxiv_id}",
        source_id=source_id,
        tier=tier,
        kind="paper",
        title=title,
        published_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.HIGH,
        content_hash=f"hash-{arxiv_id}-{source_id}",
        raw_json=json.dumps({"arxiv_id": arxiv_id, "source": source_id}),
    )


def create_hf_item(
    model_id: str,
    source_id: str = "hf-org",
    title: str = "Model Release",
    tier: int = 0,
) -> Item:
    """Create a Hugging Face item for testing."""
    return Item(
        url=f"https://huggingface.co/{model_id}",
        source_id=source_id,
        tier=tier,
        kind="model",
        title=title,
        published_at=datetime(2024, 1, 14, 10, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.MEDIUM,
        content_hash=f"hash-{model_id}",
        raw_json=json.dumps({"model_id": model_id}),
    )


def create_github_item(
    repo: str,
    tag: str,
    source_id: str = "github-releases",
    title: str = "Release",
    tier: int = 0,
) -> Item:
    """Create a GitHub release item for testing."""
    return Item(
        url=f"https://github.com/{repo}/releases/tag/{tag}",
        source_id=source_id,
        tier=tier,
        kind="release",
        title=title,
        published_at=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.HIGH,
        content_hash=f"hash-{repo}-{tag}",
        raw_json=json.dumps({"repo": repo, "tag": tag}),
    )


def create_official_blog_item(
    url: str,
    source_id: str = "official-blog",
    title: str = "Blog Post",
    tier: int = 0,
) -> Item:
    """Create an official blog item for testing."""
    return Item(
        url=url,
        source_id=source_id,
        tier=tier,
        kind="blog",
        title=title,
        published_at=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.HIGH,
        content_hash=f"hash-{source_id}",
        raw_json=json.dumps({"source": source_id}),
    )


class TestStoryLinkerIntegration:
    """Integration tests for StoryLinker."""

    def test_end_to_end_with_duplicates(self) -> None:
        """Test end-to-end linking with intentional duplicates."""
        # Create items with same arXiv ID from different sources
        items = [
            create_arxiv_item("2401.12345", source_id="arxiv-cs-ai"),
            create_arxiv_item("2401.12345", source_id="arxiv-cs-lg"),
            create_arxiv_item("2401.12345", source_id="arxiv-api"),
            # Different arXiv paper
            create_arxiv_item("2401.99999", title="Another Paper"),
            # HF model
            create_hf_item("meta-llama/Llama-2-7b"),
            # GitHub release
            create_github_item("openai/whisper", "v20231117"),
        ]

        entities_config = EntitiesConfig(
            entities=[
                EntityConfig(
                    id="meta",
                    name="Meta AI",
                    region=EntityRegion.INTL,
                    keywords=["Meta", "Llama"],
                    prefer_links=[LinkType.OFFICIAL, LinkType.HUGGINGFACE],
                ),
            ]
        )

        topics_config = TopicsConfig(
            prefer_primary_link_order=[
                LinkType.OFFICIAL,
                LinkType.ARXIV,
                LinkType.GITHUB,
                LinkType.HUGGINGFACE,
            ],
        )

        linker = StoryLinker(
            run_id="integration-test",
            entities_config=entities_config,
            topics_config=topics_config,
        )

        result = linker.link_items(items)

        # Should have 4 stories: one merged arXiv, one single arXiv, one HF, one GitHub
        assert result.items_in == 6
        assert result.stories_out == 4
        assert result.merges_total == 1  # One merge (the 3 arXiv items)

        # Verify state machine reached terminal
        assert linker.state == LinkerState.STORIES_FINAL

        # Verify story IDs are deterministic
        story_ids = [s.story_id for s in result.stories]
        assert "arxiv:2401.12345" in story_ids
        assert "arxiv:2401.99999" in story_ids

        # Verify merge rationale
        merged_rationale = next(
            r for r in result.rationales if r.story_id == "arxiv:2401.12345"
        )
        assert merged_rationale.items_merged == 3

    def test_entity_matching_integration(self) -> None:
        """Test entity matching works in integration."""
        items = [
            create_official_blog_item(
                "https://openai.com/blog/gpt4",
                title="GPT-4 Technical Report by OpenAI",
            ),
            create_arxiv_item("2401.12345", title="Claude 3 Opus from Anthropic"),
        ]

        entities_config = EntitiesConfig(
            entities=[
                EntityConfig(
                    id="openai",
                    name="OpenAI",
                    region=EntityRegion.INTL,
                    keywords=["OpenAI", "GPT-4", "GPT"],
                    prefer_links=[LinkType.OFFICIAL],
                ),
                EntityConfig(
                    id="anthropic",
                    name="Anthropic",
                    region=EntityRegion.INTL,
                    keywords=["Anthropic", "Claude"],
                    prefer_links=[LinkType.OFFICIAL, LinkType.ARXIV],
                ),
            ]
        )

        linker = StoryLinker(
            run_id="entity-test",
            entities_config=entities_config,
        )

        result = linker.link_items(items)

        # Find stories by entity
        openai_stories = [s for s in result.stories if "openai" in s.entities]
        anthropic_stories = [s for s in result.stories if "anthropic" in s.entities]

        assert len(openai_stories) == 1
        assert len(anthropic_stories) == 1

    def test_primary_link_selection(self) -> None:
        """Test primary link is selected correctly."""
        # Create items that will merge (both have same arXiv ID in URL)
        items = [
            Item(
                url="https://arxiv.org/abs/2401.12345",
                source_id="arxiv-rss",
                tier=1,
                kind="paper",
                title="Paper (arXiv RSS)",
                content_hash="hash1",
                raw_json="{}",
                date_confidence=DateConfidence.HIGH,
            ),
            Item(
                url="https://arxiv.org/abs/2401.12345",
                source_id="arxiv-api",
                tier=1,
                kind="paper",
                title="Paper (arXiv API)",
                content_hash="hash2",
                raw_json="{}",
                date_confidence=DateConfidence.HIGH,
            ),
        ]

        topics_config = TopicsConfig(
            prefer_primary_link_order=[
                LinkType.OFFICIAL,
                LinkType.ARXIV,
                LinkType.GITHUB,
            ],
        )

        linker = StoryLinker(run_id="primary-test", topics_config=topics_config)
        result = linker.link_items(items)

        # Should merge into one story (same arXiv ID)
        assert result.stories_out == 1

        # Primary link should be arxiv type
        story = result.stories[0]
        assert story.primary_link.link_type == LinkType.ARXIV

    def test_idempotency(self) -> None:
        """Test that linking is idempotent."""
        items = [
            create_arxiv_item("2401.11111"),
            create_arxiv_item("2401.22222"),
            create_hf_item("openai/gpt2"),
            create_github_item("meta-llama/llama", "v2.0"),
        ]

        linker1 = StoryLinker(run_id="run1")
        result1 = linker1.link_items(items)

        linker2 = StoryLinker(run_id="run2")
        result2 = linker2.link_items(items)

        # Results should be identical
        assert result1.stories_out == result2.stories_out

        # Story IDs should match
        ids1 = sorted([s.story_id for s in result1.stories])
        ids2 = sorted([s.story_id for s in result2.stories])
        assert ids1 == ids2

        # Primary links should match
        primaries1 = sorted([s.primary_link.url for s in result1.stories])
        primaries2 = sorted([s.primary_link.url for s in result2.stories])
        assert primaries1 == primaries2


class TestLinkerPersistenceIntegration:
    """Integration tests for LinkerPersistence."""

    def test_write_daily_json(self) -> None:
        """Test writing daily.json."""
        items = [
            create_arxiv_item("2401.12345"),
            create_hf_item("meta-llama/Llama-2-7b"),
        ]

        linker = StoryLinker(run_id="persistence-test")
        result = linker.link_items(items)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            daily_path, checksum = write_daily_json(
                result.stories,
                output_dir,
                "persistence-test",
            )

            assert daily_path.exists()
            assert len(checksum) == 64  # SHA-256 hex

            # Verify JSON content
            with daily_path.open() as f:
                data = json.load(f)

            assert data["version"] == "1.0"
            assert data["run_id"] == "persistence-test"
            assert data["story_count"] == 2
            assert len(data["stories"]) == 2

    def test_persistence_end_to_end(self) -> None:
        """Test full persistence workflow."""
        items = [create_arxiv_item("2401.12345")]

        linker = StoryLinker(run_id="full-persistence")
        result = linker.link_items(items)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "public"
            feature_dir = Path(tmpdir) / "features" / "test"

            persistence = LinkerPersistence(
                run_id="full-persistence",
                output_dir=output_dir,
                feature_dir=feature_dir,
                git_commit="abc123",
            )

            daily_path, checksum = persistence.persist_result(result)

            # Verify files exist
            assert daily_path.exists()
            assert (feature_dir / "STATE.md").exists()

            # Verify STATE.md content
            state_content = (feature_dir / "STATE.md").read_text()
            assert "P1_DONE_DEPLOYED" in state_content
            assert "abc123" in state_content
            assert checksum in state_content
