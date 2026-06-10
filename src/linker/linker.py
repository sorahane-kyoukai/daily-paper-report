"""Core Story linker for cross-source deduplication and aggregation."""

from datetime import datetime

import structlog

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.entities import EntitiesConfig, EntityConfig
from src.features.config.schemas.topics import TopicsConfig
from src.features.store.models import Item
from src.linker.constants import ALLOWLISTED_LINK_TYPES, DEFAULT_PRIMARY_LINK_ORDER
from src.linker.entity_matcher import (
    get_all_entity_ids,
    match_item_to_entities,
)
from src.linker.metrics import LinkerMetrics
from src.linker.models import (
    CandidateGroup,
    LinkerResult,
    MergeRationale,
    Story,
    StoryLink,
    TaggedItem,
)
from src.linker.state_machine import LinkerState, LinkerStateMachine
from src.linker.story_id import (
    extract_all_stable_ids,
    extract_stable_id,
    generate_story_id,
)


logger = structlog.get_logger()


# URL pattern to LinkType mapping
_URL_PATTERNS: dict[str, LinkType] = {
    "arxiv.org": LinkType.ARXIV,
    "github.com": LinkType.GITHUB,
    "huggingface.co": LinkType.HUGGINGFACE,
    "modelscope.cn": LinkType.MODELSCOPE,
    "openreview.net": LinkType.OPENREVIEW,
}

# Source kind to LinkType mapping
_KIND_LINK_TYPES: dict[str, LinkType] = {
    "blog": LinkType.BLOG,
    "news": LinkType.BLOG,
    "paper": LinkType.PAPER,
    "docs": LinkType.DOCS,
    "release": LinkType.GITHUB,
}


def _infer_link_type(item: Item) -> LinkType:
    """Infer link type from item URL and source.

    Args:
        item: Item to infer link type from.

    Returns:
        Inferred LinkType.
    """
    url_lower = item.url.lower()

    # Check URL patterns using mapping
    for pattern, link_type in _URL_PATTERNS.items():
        if pattern in url_lower:
            return link_type

    # Check source kind using mapping
    kind_link_type = _KIND_LINK_TYPES.get(item.kind.lower())
    if kind_link_type:
        return kind_link_type

    # Default to official for tier 0, otherwise blog
    return LinkType.OFFICIAL if item.tier == 0 else LinkType.BLOG


def _create_story_link(item: Item, link_type: LinkType | None = None) -> StoryLink:
    """Create a StoryLink from an Item.

    Args:
        item: Source item.
        link_type: Optional explicit link type.

    Returns:
        StoryLink instance.
    """
    if link_type is None:
        link_type = _infer_link_type(item)

    return StoryLink(
        url=item.url,
        link_type=link_type,
        source_id=item.source_id,
        tier=item.tier,
        title=item.title,
    )


def _dedupe_links(links: list[StoryLink]) -> list[StoryLink]:
    """Remove duplicate links with same type and URL.

    Args:
        links: List of links to dedupe.

    Returns:
        Deduplicated links.
    """
    seen: set[tuple[LinkType, str]] = set()
    deduped: list[StoryLink] = []

    for link in links:
        key = (link.link_type, link.url)
        if key not in seen:
            seen.add(key)
            deduped.append(link)

    return deduped


def _select_primary_link(
    links: list[StoryLink],
    prefer_order: list[str],
) -> StoryLink:
    """Select primary link based on precedence rules.

    Priority:
    1. Link type order from prefer_order
    2. Lower tier preferred
    3. First in list as fallback

    Args:
        links: Available links.
        prefer_order: Preferred link type order.

    Returns:
        Selected primary link.
    """
    if not links:
        msg = "Cannot select primary link from empty list"
        raise ValueError(msg)

    if len(links) == 1:
        return links[0]

    # Filter to allowlisted link types
    allowlisted = [
        link for link in links if link.link_type.value in ALLOWLISTED_LINK_TYPES
    ]

    if not allowlisted:
        # Fall back to first link if none are allowlisted
        return links[0]

    # Build priority score for each link
    def link_priority(link: StoryLink) -> tuple[int, int]:
        try:
            type_priority = prefer_order.index(link.link_type.value)
        except ValueError:
            type_priority = len(prefer_order)  # Not in list = lowest priority
        return (type_priority, link.tier)

    sorted_links = sorted(allowlisted, key=link_priority)
    return sorted_links[0]


class StoryLinker:
    """Story linker for cross-source deduplication and aggregation.

    Links related items from multiple sources into unified Story objects
    with deterministic story_id, primary_link selection, and entity matching.
    """

    def __init__(
        self,
        run_id: str,
        entities_config: EntitiesConfig | None = None,
        topics_config: TopicsConfig | None = None,
        metrics: LinkerMetrics | None = None,
    ) -> None:
        """Initialize the Story linker.

        Args:
            run_id: Run identifier for logging.
            entities_config: Entity configuration for matching.
            topics_config: Topics configuration for primary link order.
            metrics: Optional metrics instance for dependency injection.
        """
        self._run_id = run_id
        self._entities = entities_config.entities if entities_config else []
        self._topics = topics_config

        # Get primary link order from config or use default
        # Convert LinkType to strings for consistent handling
        if topics_config and topics_config.prefer_primary_link_order:
            self._prefer_order: list[str] = [
                lt.value for lt in topics_config.prefer_primary_link_order
            ]
        else:
            self._prefer_order = DEFAULT_PRIMARY_LINK_ORDER

        self._metrics = metrics or LinkerMetrics.get_instance()
        self._state_machine = LinkerStateMachine(run_id)
        self._log = logger.bind(
            component="linker",
            run_id=run_id,
        )

    @property
    def state(self) -> LinkerState:
        """Get current linker state."""
        return self._state_machine.state

    def link_items(self, items: list[Item]) -> LinkerResult:
        """Link items into Stories.

        This is the main entry point for the linker.

        Args:
            items: Items to link.

        Returns:
            LinkerResult with merged stories and statistics.
        """
        self._log.info("linker_started", items_in=len(items))
        self._metrics.record_items_in(len(items))

        if not items:
            self._transition_through_all_states()
            return LinkerResult(
                stories=[],
                items_in=0,
                stories_out=0,
            )

        # Phase 1: Tag items with entities
        tagged_items = self._tag_items(items)
        self._state_machine.to_entity_tagged()

        # Phase 2: Group items into candidates
        groups = self._group_candidates(tagged_items)
        self._state_machine.to_candidate_grouped()

        # Phase 3: Merge groups into stories
        stories, rationales = self._merge_groups(groups)
        self._state_machine.to_stories_merged()

        # Phase 4: Finalize
        sorted_stories = self._finalize_stories(stories)
        self._state_machine.to_stories_final()

        # Calculate stats
        merges_total = sum(1 for r in rationales if r.items_merged > 1)
        fallback_merges = sum(1 for r in rationales if r.fallback_heuristic is not None)

        self._metrics.record_stories_out(len(sorted_stories))

        self._log.info(
            "linker_complete",
            items_in=len(items),
            stories_out=len(sorted_stories),
            merges_total=merges_total,
            fallback_merges=fallback_merges,
        )

        return LinkerResult(
            stories=sorted_stories,
            items_in=len(items),
            stories_out=len(sorted_stories),
            merges_total=merges_total,
            fallback_merges=fallback_merges,
            rationales=rationales,
        )

    def _transition_through_all_states(self) -> None:
        """Transition through all states for empty input."""
        self._state_machine.to_entity_tagged()
        self._state_machine.to_candidate_grouped()
        self._state_machine.to_stories_merged()
        self._state_machine.to_stories_final()

    def _tag_items(self, items: list[Item]) -> list[TaggedItem]:
        """Tag items with entity matches and stable IDs.

        Args:
            items: Items to tag.

        Returns:
            List of tagged items.
        """
        tagged: list[TaggedItem] = []

        for item in items:
            # Match to entities
            matches = match_item_to_entities(item, self._entities)
            entity_ids = get_all_entity_ids(matches)

            # Extract stable ID
            stable_id, id_type = extract_stable_id(item)

            tagged.append(
                TaggedItem(
                    item=item,
                    entity_matches=matches,
                    entity_ids=entity_ids,
                    stable_id=stable_id,
                    stable_id_type=id_type,
                )
            )

        return tagged

    def _group_candidates(
        self, tagged_items: list[TaggedItem]
    ) -> dict[str, CandidateGroup]:
        """Group items into candidate clusters for merging.

        Groups by stable ID (arXiv, GitHub, HF) when available.

        Args:
            tagged_items: Tagged items to group.

        Returns:
            Dictionary of group_key -> CandidateGroup.
        """
        groups: dict[str, CandidateGroup] = {}

        for tagged in tagged_items:
            # Use stable ID as group key, or generate fallback key
            if tagged.stable_id:
                group_key = tagged.stable_id
            else:
                # Fallback: use story_id generation for single item
                story_id, _ = generate_story_id([tagged.item], tagged.entity_ids)
                group_key = story_id

            if group_key not in groups:
                groups[group_key] = CandidateGroup(group_key=group_key)

            groups[group_key].items.append(tagged.item)
            groups[group_key].tagged_items.append(tagged)

        return groups

    def _merge_groups(
        self, groups: dict[str, CandidateGroup]
    ) -> tuple[list[Story], list[MergeRationale]]:
        """Merge candidate groups into Stories.

        Args:
            groups: Candidate groups to merge.

        Returns:
            Tuple of (stories, rationales).
        """
        stories: list[Story] = []
        rationales: list[MergeRationale] = []

        for group_key, group in groups.items():
            story, rationale = self._create_story_from_group(group)
            stories.append(story)
            rationales.append(rationale)

            if len(group.items) > 1:
                is_fallback = "fallback:" in group_key
                self._metrics.record_merge(is_fallback=is_fallback)

        return stories, rationales

    def _collect_entity_ids(self, tagged_items: list[TaggedItem]) -> list[str]:
        """Collect unique entity IDs from tagged items."""
        all_entity_ids: list[str] = []
        for tagged in tagged_items:
            for eid in tagged.entity_ids:
                if eid not in all_entity_ids:
                    all_entity_ids.append(eid)
        return all_entity_ids

    def _get_best_published_at(self, items: list[Item]) -> datetime | None:
        """Get best published_at from items (prefer high confidence)."""
        for item in sorted(items, key=lambda i: i.date_confidence.value):
            if item.published_at:
                return item.published_at
        return None

    def _create_story_from_group(
        self, group: CandidateGroup
    ) -> tuple[Story, MergeRationale]:
        """Create a Story from a candidate group.

        Args:
            group: Candidate group to convert.

        Returns:
            Tuple of (Story, MergeRationale).
        """
        items = group.items
        all_entity_ids = self._collect_entity_ids(group.tagged_items)
        story_id, id_type = generate_story_id(items, all_entity_ids)

        # Create and dedupe links
        all_links = [_create_story_link(item) for item in items]
        deduped_links = _dedupe_links(all_links)
        primary_link = _select_primary_link(deduped_links, self._prefer_order)

        # Extract additional fields
        best_published_at = self._get_best_published_at(items)
        stable_ids = extract_all_stable_ids(items)

        rationale = MergeRationale(
            story_id=story_id,
            matched_entity_ids=all_entity_ids,
            matched_stable_ids=stable_ids.to_dict(),
            fallback_heuristic="title+entity+date" if id_type == "fallback" else None,
            source_ids=[item.source_id for item in items],
            items_merged=len(items),
        )

        story = Story(
            story_id=story_id,
            title=primary_link.title or items[0].title,
            primary_link=primary_link,
            links=deduped_links,
            entities=all_entity_ids,
            published_at=best_published_at,
            arxiv_id=stable_ids.arxiv_id,
            hf_model_id=stable_ids.hf_model_id,
            github_release_url=stable_ids.github_release_url,
            item_count=len(items),
            raw_items=items,
        )

        return story, rationale

    def _finalize_stories(self, stories: list[Story]) -> list[Story]:
        """Finalize and sort stories for output.

        Sorting order:
        1. Stories with dates come first (sorted by date descending, then story_id)
        2. Stories without dates come last (sorted by story_id ascending)

        Args:
            stories: Stories to finalize.

        Returns:
            Sorted stories.
        """
        # Partition stories by whether they have a published_at date
        dated = [s for s in stories if s.published_at is not None]
        undated = [s for s in stories if s.published_at is None]

        # Dated: descending by date, then ascending by story_id for ties
        # Using reverse=True with (date, story_id) tuple gives us:
        # - Newer dates first (descending)
        # - For same dates, story_id descending (acceptable for determinism)
        dated.sort(
            key=lambda s: (s.published_at, s.story_id) if s.published_at else ("", ""),
            reverse=True,
        )

        # Undated: ascending by story_id for stable deterministic order
        undated.sort(key=lambda s: s.story_id)

        return dated + undated


def link_items_pure(
    items: list[Item],
    entities: list[EntityConfig],
    prefer_primary_link_order: list[str],
    run_id: str = "pure",
) -> LinkerResult:
    """Pure function API for Story linking.

    Provides a testable, stateless interface for linking items.

    Args:
        items: Items to link.
        entities: Entity configurations.
        prefer_primary_link_order: Primary link type precedence.
        run_id: Run identifier for logging.

    Returns:
        LinkerResult with merged stories.
    """
    # Create minimal configs
    entities_config = EntitiesConfig(entities=entities)
    topics_config = TopicsConfig(
        prefer_primary_link_order=prefer_primary_link_order,
    )

    linker = StoryLinker(
        run_id=run_id,
        entities_config=entities_config,
        topics_config=topics_config,
    )

    return linker.link_items(items)
