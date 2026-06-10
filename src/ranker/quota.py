"""Quota filtering and source throttling for the ranker."""

import json
from collections import defaultdict

import structlog

from src.features.config.schemas.topics import QuotasConfig
from src.linker.models import Story, StorySection
from src.ranker.constants import ARXIV_CATEGORY_PATTERNS
from src.ranker.models import DroppedEntry, ScoredStory


logger = structlog.get_logger()


def _extract_arxiv_category(story: Story) -> str | None:
    """Extract arXiv category from story if present.

    Args:
        story: Story to check.

    Returns:
        arXiv category (e.g., 'cs.AI') or None.
    """
    if not story.arxiv_id:
        return None

    # Check URL for category hints
    url = story.primary_link.url.lower()
    for cat in ARXIV_CATEGORY_PATTERNS:
        if cat.lower() in url:
            return cat

    # Check raw_json for categories
    for item in story.raw_items:
        for cat in ARXIV_CATEGORY_PATTERNS:
            if cat in item.raw_json:
                return cat

    return "unknown"


def _get_source_id(story: Story) -> str:
    """Get primary source ID from story.

    Args:
        story: Story to extract source from.

    Returns:
        Source ID string.
    """
    return story.primary_link.source_id


class QuotaFilter:
    """Applies quota constraints to scored stories.

    Enforces:
    - paper_exclusion_keywords: Exclude paper-like stories by keyword
    - top5_max: Maximum items in Top 5
    - radar_max: Maximum items in Radar
    - per_source_max: Maximum items per source
    - arxiv_per_category_max: Maximum arXiv items per category

    Papers with LLM raw score >= llm_bypass_threshold bypass the
    arxiv_per_category_max quota to prevent high-quality papers from
    being dropped due to category crowding.
    """

    def __init__(
        self,
        run_id: str,
        quotas_config: QuotasConfig,
        llm_relevance_weight: float = 0.0,
    ) -> None:
        """Initialize the quota filter.

        Args:
            run_id: Run identifier for logging.
            quotas_config: Quotas configuration.
            llm_relevance_weight: Weight applied to raw LLM scores, used to
                compute the raw score from the weighted score stored in
                ScoreComponents.
        """
        self._run_id = run_id
        self._quotas = quotas_config
        self._llm_relevance_weight = llm_relevance_weight
        self._log = logger.bind(
            component="ranker",
            subcomponent="quota",
            run_id=run_id,
        )
        self._dropped: list[DroppedEntry] = []

    @property
    def dropped_entries(self) -> list[DroppedEntry]:
        """Get list of dropped entries."""
        return self._dropped

    def apply_quotas(
        self, scored_stories: list[ScoredStory]
    ) -> tuple[list[ScoredStory], list[ScoredStory]]:
        """Apply all quota constraints.

        Args:
            scored_stories: Scored stories sorted by score descending.

        Returns:
            Tuple of (kept stories, dropped stories).
        """
        self._dropped = []

        # Sort by score descending first
        sorted_stories = self._sort_by_score(scored_stories)

        # Exclude configured paper domains before quota accounting
        after_exclusion, excluded = self._apply_paper_exclusions(sorted_stories)

        # Apply per-source quota
        after_source = self._apply_per_source_quota(after_exclusion)

        # Apply arXiv per-category quota
        after_arxiv = self._apply_arxiv_category_quota(after_source)

        # Separate kept and dropped
        kept = [s for s in after_arxiv if not s.dropped]
        dropped = excluded + [s for s in after_arxiv if s.dropped]

        self._log.info(
            "quota_filtering_complete",
            input_count=len(scored_stories),
            kept_count=len(kept),
            dropped_count=len(dropped),
        )

        return kept, dropped

    def _apply_paper_exclusions(
        self, stories: list[ScoredStory]
    ) -> tuple[list[ScoredStory], list[ScoredStory]]:
        """Drop paper-like stories that match configured exclusion keywords."""
        if not self._quotas.paper_exclusion_keywords:
            return stories, []

        kept: list[ScoredStory] = []
        dropped: list[ScoredStory] = []

        for story in stories:
            matched_keyword = self._get_paper_exclusion_keyword(story.story)
            if matched_keyword is None:
                kept.append(story)
                continue

            dropped_story = ScoredStory(
                story=story.story,
                components=story.components,
                assigned_section=story.assigned_section,
                dropped=True,
                drop_reason=f"paper_exclusion_keyword ({matched_keyword})",
            )
            dropped.append(dropped_story)
            self._record_drop(story, f"paper_exclusion_keyword:{matched_keyword}")

        if dropped:
            self._log.info(
                "paper_exclusions_applied",
                dropped_count=len(dropped),
            )

        return kept, dropped

    def _sort_by_score(self, stories: list[ScoredStory]) -> list[ScoredStory]:
        """Sort stories by score with deterministic tie-breaker.

        Order:
        1. Score descending
        2. published_at descending (NULL last)
        3. primary_link URL ascending

        Args:
            stories: Stories to sort.

        Returns:
            Sorted stories.
        """

        def sort_key(s: ScoredStory) -> tuple[float, float, str]:
            # Negative score for descending
            score = -s.components.total_score

            # Published_at: negative timestamp for descending, inf for NULL (last)
            if s.story.published_at is not None:
                pub_key = -s.story.published_at.timestamp()
            else:
                pub_key = float("inf")

            # URL ascending for final tie-breaker
            url = s.story.primary_link.url

            return (score, pub_key, url)

        return sorted(stories, key=sort_key)

    def _apply_per_source_quota(self, stories: list[ScoredStory]) -> list[ScoredStory]:
        """Apply per-source maximum quota.

        Papers with high LLM scores bypass the per-source limit to
        prevent quality papers from being dropped in crowded sources.

        Args:
            stories: Sorted stories.

        Returns:
            Stories with drops marked.
        """
        source_counts: dict[str, int] = defaultdict(int)
        result: list[ScoredStory] = []
        bypass_count = 0

        for s in stories:
            source_id = _get_source_id(s.story)
            current_count = source_counts[source_id]

            if current_count >= self._quotas.per_source_max:
                if self._has_llm_bypass(s):
                    source_counts[source_id] += 1
                    result.append(s)
                    bypass_count += 1
                else:
                    dropped_story = ScoredStory(
                        story=s.story,
                        components=s.components,
                        assigned_section=s.assigned_section,
                        dropped=True,
                        drop_reason=f"per_source_max ({self._quotas.per_source_max})",
                    )
                    result.append(dropped_story)
                    self._record_drop(s, f"per_source_max:{source_id}")
            else:
                source_counts[source_id] += 1
                result.append(s)

        if bypass_count > 0:
            self._log.info(
                "per_source_llm_bypass_applied",
                bypass_count=bypass_count,
                threshold=self._quotas.llm_bypass_threshold,
            )

        return result

    def _has_llm_bypass(self, scored: ScoredStory) -> bool:
        """Check if a paper's raw LLM score exceeds the bypass threshold.

        Args:
            scored: The scored story to check.

        Returns:
            True if the paper should bypass category quotas.
        """
        threshold = self._quotas.llm_bypass_threshold
        if threshold >= 1.0 or self._llm_relevance_weight <= 0.0:
            return False

        weighted_score = scored.components.llm_relevance_score
        raw_score = weighted_score / self._llm_relevance_weight
        return raw_score >= threshold

    def _apply_arxiv_category_quota(
        self, stories: list[ScoredStory]
    ) -> list[ScoredStory]:
        """Apply arXiv per-category quota.

        Papers with raw LLM score >= llm_bypass_threshold skip the per-category
        limit to prevent high-quality papers from being dropped due to category
        crowding.

        Args:
            stories: Stories after source quota.

        Returns:
            Stories with additional drops marked.
        """
        category_counts: dict[str, int] = defaultdict(int)
        result: list[ScoredStory] = []
        bypass_count = 0

        for s in stories:
            if s.dropped:
                result.append(s)
                continue

            arxiv_cat = _extract_arxiv_category(s.story)

            if arxiv_cat is not None:
                if self._has_llm_bypass(s):
                    category_counts[arxiv_cat] += 1
                    result.append(s)
                    bypass_count += 1
                elif category_counts[arxiv_cat] >= self._quotas.arxiv_per_category_max:
                    dropped_story = ScoredStory(
                        story=s.story,
                        components=s.components,
                        assigned_section=s.assigned_section,
                        dropped=True,
                        drop_reason=f"arxiv_per_category_max ({self._quotas.arxiv_per_category_max})",
                    )
                    result.append(dropped_story)
                    self._record_drop(s, f"arxiv_category:{arxiv_cat}", arxiv_cat)
                else:
                    category_counts[arxiv_cat] += 1
                    result.append(s)
            else:
                result.append(s)

        if bypass_count > 0:
            self._log.info(
                "llm_bypass_applied",
                bypass_count=bypass_count,
                threshold=self._quotas.llm_bypass_threshold,
            )

        return result

    def _record_drop(
        self,
        scored: ScoredStory,
        reason: str,
        arxiv_category: str | None = None,
    ) -> None:
        """Record a dropped story.

        Args:
            scored: The dropped story.
            reason: Reason for dropping.
            arxiv_category: arXiv category if applicable.
        """
        entry = DroppedEntry(
            story_id=scored.story.story_id,
            source_id=_get_source_id(scored.story),
            score=scored.components.total_score,
            drop_reason=reason,
            arxiv_category=arxiv_category,
        )
        self._dropped.append(entry)

    def _get_paper_exclusion_keyword(self, story: Story) -> str | None:
        """Return the matching exclusion keyword for a paper-like story."""
        if not self._is_paper(story):
            return None

        search_text = self._build_story_search_text(story)
        for keyword in self._quotas.paper_exclusion_keywords:
            normalized = keyword.casefold().strip()
            if normalized and normalized in search_text:
                return keyword
        return None

    def _build_story_search_text(self, story: Story) -> str:
        """Build searchable text from title, abstract, and categories."""
        parts = [story.title]

        for item in story.raw_items:
            parts.append(item.title)
            try:
                raw = json.loads(item.raw_json) if item.raw_json else {}
            except (json.JSONDecodeError, TypeError):
                raw = {}

            for field_name in ("abstract_snippet", "summary", "feed_category"):
                value = raw.get(field_name)
                if isinstance(value, str) and value:
                    parts.append(value)

            categories = raw.get("categories")
            if isinstance(categories, list):
                parts.extend(str(category) for category in categories if category)
            elif isinstance(categories, str) and categories:
                parts.append(categories)

        return " ".join(parts).casefold()

    def assign_sections(
        self, kept_stories: list[ScoredStory]
    ) -> dict[StorySection, list[ScoredStory]]:
        """Assign stories to output sections.

        Args:
            kept_stories: Stories that passed quota filtering.

        Returns:
            Dictionary of section -> stories.
        """
        sorted_kept = self._sort_by_score(kept_stories)
        sections = self._init_sections()
        assigned_ids: set[str] = set()

        self._assign_top5(sorted_kept, sections, assigned_ids)
        self._assign_model_releases(sorted_kept, sections, assigned_ids)
        self._assign_papers(sorted_kept, sections, assigned_ids)
        self._assign_radar(sorted_kept, sections, assigned_ids)

        self._log.info(
            "section_assignment_complete",
            top5=len(sections[StorySection.TOP5]),
            model_releases=len(sections[StorySection.MODEL_RELEASES]),
            papers=len(sections[StorySection.PAPERS]),
            radar=len(sections[StorySection.RADAR]),
        )

        return sections

    def _init_sections(self) -> dict[StorySection, list[ScoredStory]]:
        """Initialize empty sections dictionary."""
        return {
            StorySection.TOP5: [],
            StorySection.MODEL_RELEASES: [],
            StorySection.PAPERS: [],
            StorySection.RADAR: [],
        }

    def _assign_top5(
        self,
        stories: list[ScoredStory],
        sections: dict[StorySection, list[ScoredStory]],
        assigned_ids: set[str],
    ) -> None:
        """Assign highest scoring stories to Top 5."""
        for s in stories:
            if len(sections[StorySection.TOP5]) >= self._quotas.top5_max:
                break
            s.assigned_section = StorySection.TOP5
            sections[StorySection.TOP5].append(s)
            assigned_ids.add(s.story.story_id)

    def _assign_model_releases(
        self,
        stories: list[ScoredStory],
        sections: dict[StorySection, list[ScoredStory]],
        assigned_ids: set[str],
    ) -> None:
        """Assign model releases to MODEL_RELEASES section."""
        for s in stories:
            if s.story.story_id in assigned_ids:
                continue
            if self._is_model_release(s.story):
                s.assigned_section = StorySection.MODEL_RELEASES
                sections[StorySection.MODEL_RELEASES].append(s)
                assigned_ids.add(s.story.story_id)

    def _assign_papers(
        self,
        stories: list[ScoredStory],
        sections: dict[StorySection, list[ScoredStory]],
        assigned_ids: set[str],
    ) -> None:
        """Assign papers to PAPERS section (up to papers_max)."""
        papers_count = 0
        for s in stories:
            if s.story.story_id in assigned_ids:
                continue
            if self._is_paper(s.story):
                if papers_count >= self._quotas.papers_max:
                    continue
                s.assigned_section = StorySection.PAPERS
                sections[StorySection.PAPERS].append(s)
                assigned_ids.add(s.story.story_id)
                papers_count += 1

    def _assign_radar(
        self,
        stories: list[ScoredStory],
        sections: dict[StorySection, list[ScoredStory]],
        assigned_ids: set[str],
    ) -> None:
        """Assign remaining stories to RADAR section.

        Remaining stories are capped by radar_max after higher-priority sections
        have been assigned.
        """
        for s in stories:
            if s.story.story_id in assigned_ids:
                continue
            if len(sections[StorySection.RADAR]) >= self._quotas.radar_max:
                s.dropped = True
                s.drop_reason = f"radar_max ({self._quotas.radar_max})"
                self._record_drop(s, "radar_max")
                continue
            s.assigned_section = StorySection.RADAR
            sections[StorySection.RADAR].append(s)
            assigned_ids.add(s.story.story_id)

    def _is_model_release(self, story: Story) -> bool:
        """Check if story is a model release.

        Args:
            story: Story to check.

        Returns:
            True if story is a model release.
        """
        # Has HF model ID
        if story.hf_model_id:
            return True

        # Has entities and kind contains 'model'
        if story.entities:
            for item in story.raw_items:
                if item.kind.lower() == "model":
                    return True

        return False

    def _is_paper(self, story: Story) -> bool:
        """Check if story is a paper.

        Args:
            story: Story to check.

        Returns:
            True if story is a paper.
        """
        if story.arxiv_id:
            return True
        return any(item.kind.lower() == "paper" for item in story.raw_items)


def apply_quotas_pure(
    scored_stories: list[ScoredStory],
    quotas_config: QuotasConfig,
    run_id: str = "pure",
    llm_relevance_weight: float = 0.0,
) -> tuple[dict[StorySection, list[ScoredStory]], list[DroppedEntry]]:
    """Pure function API for quota filtering.

    Args:
        scored_stories: Scored stories to filter.
        quotas_config: Quotas configuration.
        run_id: Run identifier.
        llm_relevance_weight: Weight applied to raw LLM scores.

    Returns:
        Tuple of (sections dict, dropped entries).
    """
    quota_filter = QuotaFilter(
        run_id=run_id,
        quotas_config=quotas_config,
        llm_relevance_weight=llm_relevance_weight,
    )
    kept, _dropped = quota_filter.apply_quotas(scored_stories)
    sections = quota_filter.assign_sections(kept)
    return sections, quota_filter.dropped_entries
