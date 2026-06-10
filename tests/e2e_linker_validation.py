"""Comprehensive E2E validation script for Story Linker feature.

This script validates all acceptance criteria for the add-story-linker-and-dedupe feature.
"""

import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.config.schemas.base import (
    LinkType,  # noqa: F401 - may be used in future tests
)
from src.features.config.schemas.entities import (
    EntitiesConfig,
    EntityConfig,
    EntityRegion,
)
from src.features.store.models import DateConfidence, Item
from src.linker.linker import StoryLinker
from src.linker.persistence import LinkerPersistence, write_daily_json
from src.linker.state_machine import LinkerState, LinkerStateTransitionError


def create_arxiv_item(
    arxiv_id: str,
    source_id: str = "arxiv-rss",
    title: str = "Test Paper",
    published_at: datetime | None = None,
) -> Item:
    """Create an arXiv item for testing."""
    return Item(
        url=f"https://arxiv.org/abs/{arxiv_id}",
        source_id=source_id,
        tier=1,
        kind="paper",
        title=title,
        published_at=published_at or datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.HIGH,
        content_hash=f"hash-{arxiv_id}-{source_id}",
        raw_json=json.dumps({"arxiv_id": arxiv_id, "source": source_id}),
    )


def create_hf_item(
    model_id: str,
    source_id: str = "hf-org",
    title: str = "Model Release",
) -> Item:
    """Create a Hugging Face item for testing."""
    return Item(
        url=f"https://huggingface.co/{model_id}",
        source_id=source_id,
        tier=0,
        kind="model",
        title=title,
        published_at=datetime(2024, 1, 14, 10, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.MEDIUM,
        content_hash=f"hash-{model_id}",
        raw_json=json.dumps({"model_id": model_id}),
    )


def create_github_item(repo: str, tag: str) -> Item:
    """Create a GitHub release item for testing."""
    return Item(
        url=f"https://github.com/{repo}/releases/tag/{tag}",
        source_id="github-releases",
        tier=0,
        kind="release",
        title=f"{repo} {tag}",
        published_at=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC),
        date_confidence=DateConfidence.HIGH,
        content_hash=f"hash-{repo}-{tag}",
        raw_json=json.dumps({"repo": repo, "tag": tag}),
    )


def verify_ac1_same_arxiv_id_produces_single_story() -> tuple[bool, str]:
    """AC1: Same arXiv ID produces single Story with primary link per precedence."""
    print("\n=== AC1: Same arXiv ID Produces Single Story ===")

    # Create 3 items with same arXiv ID from different sources
    items = [
        create_arxiv_item("2401.12345", source_id="arxiv-cs-ai"),
        create_arxiv_item("2401.12345", source_id="arxiv-cs-lg"),
        create_arxiv_item("2401.12345", source_id="arxiv-api"),
    ]

    linker = StoryLinker(run_id="ac1-test")
    result = linker.link_items(items)

    # Verify results
    checks = []

    # Check stories_out == 1
    if result.stories_out == 1:
        checks.append("PASS: stories_out == 1")
    else:
        checks.append(f"FAIL: stories_out == {result.stories_out}, expected 1")

    # Check story_id
    if result.stories[0].story_id == "arxiv:2401.12345":
        checks.append("PASS: story_id == 'arxiv:2401.12345'")
    else:
        checks.append(f"FAIL: story_id == '{result.stories[0].story_id}'")

    # Check item_count
    if result.stories[0].item_count == 3:
        checks.append("PASS: item_count == 3")
    else:
        checks.append(f"FAIL: item_count == {result.stories[0].item_count}")

    # Check merges_total
    if result.merges_total == 1:
        checks.append("PASS: merges_total == 1")
    else:
        checks.append(f"FAIL: merges_total == {result.merges_total}")

    for check in checks:
        print(f"  {check}")

    passed = all("PASS" in c for c in checks)
    return passed, "\n".join(checks)


def verify_ac2_story_ordering_deterministic() -> tuple[bool, str]:
    """AC2: Story ordering is stable and deterministic."""
    print("\n=== AC2: Story Ordering is Deterministic ===")

    # Create test items
    items = [
        create_arxiv_item("2401.11111", title="First Paper"),
        create_arxiv_item("2401.22222", title="Second Paper"),
        create_hf_item("meta-llama/Llama-2-7b"),
        create_github_item("openai/whisper", "v20231117"),
    ]

    # Run linker twice with different run_ids
    linker1 = StoryLinker(run_id="determinism-run1")
    result1 = linker1.link_items(items)

    linker2 = StoryLinker(run_id="determinism-run2")
    result2 = linker2.link_items(items)

    checks = []

    # Check same number of stories
    if result1.stories_out == result2.stories_out:
        checks.append(f"PASS: stories_out identical ({result1.stories_out})")
    else:
        checks.append(
            f"FAIL: stories_out differ ({result1.stories_out} vs {result2.stories_out})"
        )

    # Check story IDs match
    ids1 = [s.story_id for s in result1.stories]
    ids2 = [s.story_id for s in result2.stories]
    if ids1 == ids2:
        checks.append("PASS: story_ids identical")
    else:
        checks.append(f"FAIL: story_ids differ ({ids1} vs {ids2})")

    # Check primary links match
    primaries1 = [s.primary_link.url for s in result1.stories]
    primaries2 = [s.primary_link.url for s in result2.stories]
    if primaries1 == primaries2:
        checks.append("PASS: primary_links identical")
    else:
        checks.append("FAIL: primary_links differ")

    # Write to daily.json and verify story content is identical
    # Note: run_id and generated_at differ by design, so compare story content only
    output_dir = Path("/tmp/linker-e2e-test")

    path1, _ = write_daily_json(result1.stories, output_dir, "run1")
    path2, _ = write_daily_json(result2.stories, output_dir, "run2")

    # Compare story content (excluding run metadata)
    with path1.open() as f1, path2.open() as f2:
        data1 = json.load(f1)
        data2 = json.load(f2)

    # Compare stories array (the actual content that must be deterministic)
    stories_json1 = json.dumps(data1.get("stories", []), sort_keys=True)
    stories_json2 = json.dumps(data2.get("stories", []), sort_keys=True)

    story_checksum1 = hashlib.sha256(stories_json1.encode()).hexdigest()
    story_checksum2 = hashlib.sha256(stories_json2.encode()).hexdigest()

    if story_checksum1 == story_checksum2:
        checks.append(
            f"PASS: story content checksums identical ({story_checksum1[:16]}...)"
        )
    else:
        checks.append(
            f"FAIL: story content checksums differ ({story_checksum1[:16]} vs {story_checksum2[:16]})"
        )

    for check in checks:
        print(f"  {check}")

    passed = all("PASS" in c for c in checks)
    return passed, "\n".join(checks)


def verify_ac3_persistence_and_evidence() -> tuple[bool, str]:
    """AC3: Persistence to daily.json and STATE.md with evidence."""
    print("\n=== AC3: Persistence and Evidence ===")

    # Create test items with duplicates
    items = [
        create_arxiv_item("2401.12345", source_id="arxiv-rss"),
        create_arxiv_item("2401.12345", source_id="arxiv-api"),
        create_hf_item("meta-llama/Llama-2-7b"),
    ]

    linker = StoryLinker(run_id="ac3-test")
    result = linker.link_items(items)

    # Persist results
    output_dir = Path("/tmp/linker-e2e-test")
    feature_dir = Path("/tmp/linker-e2e-test/features/add-story-linker-and-dedupe")

    persistence = LinkerPersistence(
        run_id="ac3-test",
        output_dir=output_dir,
        feature_dir=feature_dir,
        git_commit="e2e-validation",
    )

    daily_path, checksum = persistence.persist_result(result)

    checks = []

    # Check daily.json exists
    if daily_path.exists():
        checks.append(f"PASS: daily.json exists at {daily_path}")
    else:
        checks.append("FAIL: daily.json does not exist")

    # Check daily.json content
    if daily_path.exists():
        with daily_path.open() as f:
            data = json.load(f)
        if data.get("version") == "1.0" and data.get("story_count") == 2:
            checks.append("PASS: daily.json has correct schema (2 stories)")
        else:
            checks.append(
                f"FAIL: daily.json schema incorrect (got {data.get('story_count')} stories)"
            )

    # Check STATE.md exists
    state_path = feature_dir / "STATE.md"
    if state_path.exists():
        checks.append("PASS: STATE.md exists")
        content = state_path.read_text()
        if "P1_DONE_DEPLOYED" in content:
            checks.append("PASS: STATE.md contains status")
        else:
            checks.append("FAIL: STATE.md missing status")
    else:
        checks.append("FAIL: STATE.md does not exist")

    # Check checksum is valid
    if len(checksum) == 64:
        checks.append(f"PASS: SHA-256 checksum valid ({checksum[:16]}...)")
    else:
        checks.append("FAIL: checksum invalid")

    for check in checks:
        print(f"  {check}")

    passed = all("PASS" in c for c in checks)
    return passed, "\n".join(checks)


def verify_entity_matching() -> tuple[bool, str]:
    """Verify entity matching works correctly."""
    print("\n=== Entity Matching ===")

    entities_config = EntitiesConfig(
        entities=[
            EntityConfig(
                id="openai",
                name="OpenAI",
                region=EntityRegion.INTL,
                keywords=["OpenAI", "GPT-4", "ChatGPT"],
                prefer_links=[LinkType.OFFICIAL],
            ),
            EntityConfig(
                id="anthropic",
                name="Anthropic",
                region=EntityRegion.INTL,
                keywords=["Anthropic", "Claude"],
                prefer_links=[LinkType.OFFICIAL],
            ),
        ]
    )

    items = [
        Item(
            url="https://example.com/openai-post",
            source_id="blog",
            tier=1,
            kind="blog",
            title="OpenAI announces GPT-4 Turbo",
            content_hash="hash1",
            raw_json="{}",
            date_confidence=DateConfidence.HIGH,
        ),
        Item(
            url="https://example.com/anthropic-post",
            source_id="blog",
            tier=1,
            kind="blog",
            title="Anthropic releases Claude 3",
            content_hash="hash2",
            raw_json="{}",
            date_confidence=DateConfidence.HIGH,
        ),
    ]

    linker = StoryLinker(run_id="entity-test", entities_config=entities_config)
    result = linker.link_items(items)

    checks = []

    # Check OpenAI entity matched
    openai_stories = [s for s in result.stories if "openai" in s.entities]
    if len(openai_stories) == 1:
        checks.append("PASS: OpenAI entity matched to 1 story")
    else:
        checks.append(f"FAIL: OpenAI matched to {len(openai_stories)} stories")

    # Check Anthropic entity matched
    anthropic_stories = [s for s in result.stories if "anthropic" in s.entities]
    if len(anthropic_stories) == 1:
        checks.append("PASS: Anthropic entity matched to 1 story")
    else:
        checks.append(f"FAIL: Anthropic matched to {len(anthropic_stories)} stories")

    for check in checks:
        print(f"  {check}")

    passed = all("PASS" in c for c in checks)
    return passed, "\n".join(checks)


def verify_state_machine() -> tuple[bool, str]:
    """Verify state machine transitions work correctly."""
    print("\n=== State Machine ===")

    checks = []

    # Test valid transition sequence
    linker = StoryLinker(run_id="state-test")
    items = [create_arxiv_item("2401.12345")]
    _ = linker.link_items(items)  # Execute to change state

    if linker.state == LinkerState.STORIES_FINAL:
        checks.append("PASS: Linker reaches STORIES_FINAL state")
    else:
        checks.append(f"FAIL: Linker in state {linker.state}")

    # Test invalid transition raises error
    from src.linker.state_machine import LinkerStateMachine

    sm = LinkerStateMachine(run_id="invalid-test")
    try:
        sm.to_stories_final()  # Invalid: can't skip states
        checks.append("FAIL: Invalid transition did not raise error")
    except LinkerStateTransitionError:
        checks.append("PASS: Invalid transition raises LinkerStateTransitionError")

    for check in checks:
        print(f"  {check}")

    passed = all("PASS" in c for c in checks)
    return passed, "\n".join(checks)


def verify_duplicate_link_collapse() -> tuple[bool, str]:
    """Verify duplicate links are collapsed."""
    print("\n=== Duplicate Link Collapse ===")

    # Create items with same URL
    items = [
        create_arxiv_item("2401.12345", source_id="arxiv-rss"),
        create_arxiv_item("2401.12345", source_id="arxiv-api"),
        create_arxiv_item("2401.12345", source_id="arxiv-cs-ai"),
    ]

    linker = StoryLinker(run_id="dedupe-test")
    result = linker.link_items(items)

    checks = []

    # Should have 1 story
    if result.stories_out == 1:
        checks.append("PASS: 1 story from 3 duplicate items")
    else:
        checks.append(f"FAIL: {result.stories_out} stories, expected 1")

    # Should have only 1 link (same URL, same type)
    story = result.stories[0]
    if len(story.links) == 1:
        checks.append("PASS: 1 link after deduplication")
    else:
        checks.append(f"FAIL: {len(story.links)} links, expected 1")

    for check in checks:
        print(f"  {check}")

    passed = all("PASS" in c for c in checks)
    return passed, "\n".join(checks)


def main() -> int:
    """Run all E2E validations and report results."""
    print("=" * 60)
    print("Story Linker E2E Validation")
    print("=" * 60)

    run_id = str(uuid.uuid4())[:8]
    print(f"Run ID: {run_id}")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")

    results: list[tuple[str, bool, str]] = []

    # Run all acceptance criteria verifications
    passed, details = verify_ac1_same_arxiv_id_produces_single_story()
    results.append(("AC1: Same arXiv ID = Single Story", passed, details))

    passed, details = verify_ac2_story_ordering_deterministic()
    results.append(("AC2: Deterministic Ordering", passed, details))

    passed, details = verify_ac3_persistence_and_evidence()
    results.append(("AC3: Persistence and Evidence", passed, details))

    passed, details = verify_entity_matching()
    results.append(("Entity Matching", passed, details))

    passed, details = verify_state_machine()
    results.append(("State Machine", passed, details))

    passed, details = verify_duplicate_link_collapse()
    results.append(("Duplicate Link Collapse", passed, details))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed, _ in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("ALL ACCEPTANCE CRITERIA PASSED")
        return 0
    print("SOME ACCEPTANCE CRITERIA FAILED")
    return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
