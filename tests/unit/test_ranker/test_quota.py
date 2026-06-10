"""Unit tests for ranker quota filtering."""

from datetime import UTC, datetime

from src.features.config.schemas.base import LinkType
from src.features.config.schemas.topics import QuotasConfig
from src.features.store.models import DateConfidence, Item
from src.linker.models import Story, StoryLink, StorySection
from src.ranker.models import ScoreComponents, ScoredStory
from src.ranker.quota import QuotaFilter, apply_quotas_pure


def _make_item(
    url: str = "https://example.com/item",
    source_id: str = "test-source",
    tier: int = 0,
    kind: str = "blog",
    title: str = "Test Item",
    published_at: datetime | None = None,
    raw_json: str = "{}",
) -> Item:
    """Create a test Item."""
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


def _make_story(
    story_id: str = "test-story-1",
    title: str = "Test Story",
    source_id: str = "test-source",
    tier: int = 0,
    kind: str = "blog",
    entities: list[str] | None = None,
    published_at: datetime | None = None,
    arxiv_id: str | None = None,
    hf_model_id: str | None = None,
    raw_json: str = "{}",
) -> Story:
    """Create a test Story."""
    link = StoryLink(
        url=f"https://example.com/{story_id}",
        link_type=LinkType.OFFICIAL,
        source_id=source_id,
        tier=tier,
        title=title,
    )

    raw_items = [
        _make_item(
            kind=kind,
            title=title,
            published_at=published_at,
            source_id=source_id,
            raw_json=raw_json,
        )
    ]

    return Story(
        story_id=story_id,
        title=title,
        primary_link=link,
        links=[link],
        entities=entities or [],
        published_at=published_at,
        arxiv_id=arxiv_id,
        hf_model_id=hf_model_id,
        raw_items=raw_items,
    )


def _make_scored_story(
    story: Story,
    score: float = 5.0,
) -> ScoredStory:
    """Create a ScoredStory with given score."""
    components = ScoreComponents(
        tier_score=score / 5,
        kind_score=score / 5,
        topic_score=score / 5,
        recency_score=score / 5,
        entity_score=score / 5,
        total_score=score,
    )
    return ScoredStory(story=story, components=components)


class TestPerSourceQuota:
    """Tests for per-source quota enforcement."""

    def test_respects_per_source_max(self) -> None:
        """Stories over per-source limit are dropped."""
        quotas = QuotasConfig(per_source_max=2)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        # 5 stories from same source with different scores
        stories = [
            _make_scored_story(
                _make_story(story_id=f"s{i}", source_id="source-a"),
                score=10 - i,  # Decreasing scores
            )
            for i in range(5)
        ]

        kept, dropped = quota_filter.apply_quotas(stories)

        # Should keep top 2 (highest scores)
        kept_ids = [s.story.story_id for s in kept]
        assert len(kept) == 2
        assert "s0" in kept_ids  # Highest score
        assert "s1" in kept_ids  # Second highest

        # Should drop 3
        [s.story.story_id for s in dropped]
        assert len(dropped) == 3
        assert all(s.dropped for s in dropped)

    def test_multiple_sources_separate_quotas(self) -> None:
        """Each source gets its own quota."""
        quotas = QuotasConfig(per_source_max=2)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id="a1", source_id="source-a"), 10),
            _make_scored_story(_make_story(story_id="a2", source_id="source-a"), 9),
            _make_scored_story(_make_story(story_id="a3", source_id="source-a"), 8),
            _make_scored_story(_make_story(story_id="b1", source_id="source-b"), 7),
            _make_scored_story(_make_story(story_id="b2", source_id="source-b"), 6),
            _make_scored_story(_make_story(story_id="b3", source_id="source-b"), 5),
        ]

        kept, dropped = quota_filter.apply_quotas(stories)

        # 2 from each source = 4 kept
        assert len(kept) == 4
        assert len(dropped) == 2

    def test_within_quota_all_kept(self) -> None:
        """Stories within quota are all kept."""
        quotas = QuotasConfig(per_source_max=10)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id=f"s{i}"), i) for i in range(5)
        ]

        kept, dropped = quota_filter.apply_quotas(stories)

        assert len(kept) == 5
        assert len(dropped) == 0


class TestArxivCategoryQuota:
    """Tests for arXiv per-category quota."""

    def test_respects_arxiv_category_max(self) -> None:
        """arXiv stories over category limit are dropped."""
        quotas = QuotasConfig(arxiv_per_category_max=2, per_source_max=100)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(
                _make_story(
                    story_id=f"arxiv{i}",
                    arxiv_id=f"2401.{i:05d}",
                    raw_json='{"categories": "cs.AI"}',
                ),
                score=10 - i,
            )
            for i in range(5)
        ]

        kept, dropped = quota_filter.apply_quotas(stories)

        assert len(kept) == 2
        assert len(dropped) == 3


class TestDeterministicOrdering:
    """Tests for deterministic tie-breaking."""

    def test_score_descending(self) -> None:
        """Higher scores come first."""
        quotas = QuotasConfig()
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id="low"), 1),
            _make_scored_story(_make_story(story_id="high"), 10),
            _make_scored_story(_make_story(story_id="mid"), 5),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        ids = [s.story.story_id for s in kept]

        assert ids[0] == "high"
        assert ids[1] == "mid"
        assert ids[2] == "low"

    def test_published_at_tiebreaker(self) -> None:
        """Same score: newer published_at comes first."""
        quotas = QuotasConfig()
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        datetime.now(UTC)
        old_time = datetime(2024, 1, 1, tzinfo=UTC)
        new_time = datetime(2024, 1, 15, tzinfo=UTC)

        stories = [
            _make_scored_story(_make_story(story_id="old", published_at=old_time), 5),
            _make_scored_story(_make_story(story_id="new", published_at=new_time), 5),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        ids = [s.story.story_id for s in kept]

        assert ids[0] == "new"  # Newer first
        assert ids[1] == "old"

    def test_null_published_at_last(self) -> None:
        """Same score: NULL published_at comes last."""
        quotas = QuotasConfig()
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        some_time = datetime(2024, 1, 1, tzinfo=UTC)

        stories = [
            _make_scored_story(_make_story(story_id="no-date", published_at=None), 5),
            _make_scored_story(
                _make_story(story_id="has-date", published_at=some_time), 5
            ),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        ids = [s.story.story_id for s in kept]

        assert ids[0] == "has-date"  # With date first
        assert ids[1] == "no-date"  # NULL last

    def test_url_tiebreaker(self) -> None:
        """Same score and date: URL ascending is final tiebreaker."""
        quotas = QuotasConfig()
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        same_time = datetime(2024, 1, 1, tzinfo=UTC)

        stories = [
            _make_scored_story(
                _make_story(story_id="z-story", published_at=same_time), 5
            ),
            _make_scored_story(
                _make_story(story_id="a-story", published_at=same_time), 5
            ),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        ids = [s.story.story_id for s in kept]

        # URL contains story_id, so a-story < z-story alphabetically
        assert ids[0] == "a-story"
        assert ids[1] == "z-story"


class TestPaperExclusions:
    """Tests for keyword-based paper exclusion."""

    def test_medical_paper_excluded_before_section_assignment(self) -> None:
        """Medical paper-like stories are dropped before section assignment."""
        quotas = QuotasConfig(top5_max=1, per_source_max=100)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(
                _make_story(
                    story_id="medical-paper",
                    title="Clinical foundation model for radiology",
                    kind="paper",
                    raw_json=(
                        '{"summary": "A medical imaging benchmark for hospital '
                        'diagnosis workflows."}'
                    ),
                ),
                10,
            ),
            _make_scored_story(
                _make_story(
                    story_id="kept-paper",
                    title="Efficient reasoning agents for code generation",
                    kind="paper",
                    raw_json='{"summary": "A general-purpose reasoning paper."}',
                ),
                9,
            ),
        ]

        kept, dropped = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)

        assert [s.story.story_id for s in kept] == ["kept-paper"]
        assert [s.story.story_id for s in dropped] == ["medical-paper"]
        assert sections[StorySection.TOP5][0].story.story_id == "kept-paper"
        assert dropped[0].drop_reason is not None
        assert dropped[0].drop_reason.startswith("paper_exclusion_keyword (")

    def test_non_paper_medical_story_is_not_excluded(self) -> None:
        """Non-paper medical stories still follow normal section assignment."""
        quotas = QuotasConfig(top5_max=1, per_source_max=100)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(
                _make_story(
                    story_id="medical-blog",
                    title="Clinical AI deployment lessons",
                    kind="blog",
                    raw_json='{"summary": "A hospital deployment retrospective."}',
                ),
                10,
            )
        ]

        kept, dropped = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)

        assert len(dropped) == 0
        assert sections[StorySection.TOP5][0].story.story_id == "medical-blog"


class TestSectionAssignment:
    """Tests for output section assignment."""

    def test_top5_max_enforced(self) -> None:
        """Top 5 section respects max limit."""
        quotas = QuotasConfig(top5_max=5, per_source_max=100)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id=f"s{i}"), 10 - i) for i in range(10)
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)

        assert len(sections[StorySection.TOP5]) == 5

    def test_radar_max_enforced(self) -> None:
        """Overflow paper-like stories still respect radar max."""
        quotas = QuotasConfig(
            top5_max=0,
            papers_max=0,
            radar_max=3,
            per_source_max=100,
        )
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id=f"s{i}", kind="paper"), 10 - i)
            for i in range(10)
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)

        assert len(sections[StorySection.TOP5]) == 0
        assert len(sections[StorySection.RADAR]) <= 3

    def test_non_paper_updates_respect_radar_max(self) -> None:
        """Non-paper site updates still respect radar max."""
        quotas = QuotasConfig(
            top5_max=0,
            papers_max=0,
            radar_max=1,
            per_source_max=100,
        )
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id="blog-1", kind="blog"), 10),
            _make_scored_story(_make_story(story_id="blog-2", kind="blog"), 9),
            _make_scored_story(_make_story(story_id="blog-3", kind="blog"), 8),
            _make_scored_story(_make_story(story_id="paper-1", kind="paper"), 7),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)
        radar_ids = [s.story.story_id for s in sections[StorySection.RADAR]]

        assert radar_ids == ["blog-1"]
        assert [entry.story_id for entry in quota_filter.dropped_entries] == [
            "blog-2",
            "blog-3",
            "paper-1",
        ]
        assert all(
            entry.drop_reason == "radar_max" for entry in quota_filter.dropped_entries
        )

    def test_papers_assigned_correctly(self) -> None:
        """Papers are assigned to PAPERS section."""
        quotas = QuotasConfig(top5_max=1, per_source_max=100)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id="top", kind="blog"), 10),
            _make_scored_story(_make_story(story_id="paper1", kind="paper"), 5),
            _make_scored_story(
                _make_story(story_id="paper2", arxiv_id="2401.00001"), 4
            ),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)

        paper_ids = [s.story.story_id for s in sections[StorySection.PAPERS]]
        assert "paper1" in paper_ids
        assert "paper2" in paper_ids

    def test_model_releases_assigned_correctly(self) -> None:
        """Model releases are assigned to MODEL_RELEASES section."""
        quotas = QuotasConfig(top5_max=1, per_source_max=100)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id="top", kind="blog"), 10),
            _make_scored_story(
                _make_story(
                    story_id="model1",
                    kind="model",
                    hf_model_id="openai/gpt-4",
                    entities=["openai"],
                ),
                5,
            ),
        ]

        kept, _ = quota_filter.apply_quotas(stories)
        sections = quota_filter.assign_sections(kept)

        model_ids = [s.story.story_id for s in sections[StorySection.MODEL_RELEASES]]
        assert "model1" in model_ids


class TestDroppedEntries:
    """Tests for dropped entry tracking."""

    def test_dropped_entries_recorded(self) -> None:
        """Dropped stories are recorded with details."""
        quotas = QuotasConfig(per_source_max=1)
        quota_filter = QuotaFilter(run_id="test", quotas_config=quotas)

        stories = [
            _make_scored_story(_make_story(story_id="kept", source_id="src"), 10),
            _make_scored_story(_make_story(story_id="dropped", source_id="src"), 5),
        ]

        quota_filter.apply_quotas(stories)
        dropped = quota_filter.dropped_entries

        assert len(dropped) == 1
        assert dropped[0].story_id == "dropped"
        assert dropped[0].source_id == "src"
        assert dropped[0].score == 5.0
        assert "per_source_max" in dropped[0].drop_reason


class TestLlmBypass:
    """Tests for LLM score bypass of arXiv category quota."""

    def _make_arxiv_scored(
        self,
        story_id: str,
        category: str,
        total_score: float,
        llm_weighted: float,
    ) -> ScoredStory:
        """Create a scored arXiv story with specific LLM weighted score."""
        story = _make_story(
            story_id=story_id,
            source_id="arxiv",
            arxiv_id=story_id.replace("arxiv:", ""),
            kind="paper",
            raw_json=f'{{"category": "{category}"}}',
        )
        components = ScoreComponents(
            tier_score=1.0,
            kind_score=1.0,
            topic_score=2.0,
            recency_score=1.0,
            entity_score=0.0,
            llm_relevance_score=llm_weighted,
            total_score=total_score,
        )
        return ScoredStory(story=story, components=components)

    def test_high_llm_score_bypasses_category_quota(self) -> None:
        """Papers above LLM bypass threshold skip category quota."""
        quotas = QuotasConfig(
            arxiv_per_category_max=2,
            per_source_max=100,
            llm_bypass_threshold=0.70,
        )
        llm_weight = 18.0
        quota_filter = QuotaFilter(
            run_id="test",
            quotas_config=quotas,
            llm_relevance_weight=llm_weight,
        )

        stories = [
            self._make_arxiv_scored("s1", "cs.AI", 30.0, 0.90 * llm_weight),
            self._make_arxiv_scored("s2", "cs.AI", 25.0, 0.80 * llm_weight),
            self._make_arxiv_scored("s3", "cs.AI", 20.0, 0.75 * llm_weight),
            self._make_arxiv_scored("s4", "cs.AI", 15.0, 0.50 * llm_weight),
        ]

        kept, dropped = quota_filter.apply_quotas(stories)
        kept_ids = {s.story.story_id for s in kept}

        # s1 (0.90), s2 (0.80), s3 (0.75) all bypass because >= 0.70
        # s4 (0.50) is below threshold and category count (3) > max (2) -> dropped
        assert "s1" in kept_ids
        assert "s2" in kept_ids
        assert "s3" in kept_ids
        assert len(dropped) == 1
        assert dropped[0].story.story_id == "s4"

    def test_bypass_disabled_when_threshold_is_one(self) -> None:
        """Setting threshold to 1.0 disables bypass."""
        quotas = QuotasConfig(
            arxiv_per_category_max=2,
            per_source_max=100,
            llm_bypass_threshold=1.0,
        )
        llm_weight = 18.0
        quota_filter = QuotaFilter(
            run_id="test",
            quotas_config=quotas,
            llm_relevance_weight=llm_weight,
        )

        stories = [
            self._make_arxiv_scored("s1", "cs.AI", 30.0, 0.90 * llm_weight),
            self._make_arxiv_scored("s2", "cs.AI", 25.0, 0.80 * llm_weight),
            self._make_arxiv_scored("s3", "cs.AI", 20.0, 0.75 * llm_weight),
        ]

        kept, dropped = quota_filter.apply_quotas(stories)

        assert len(kept) == 2
        assert len(dropped) == 1

    def test_bypass_with_zero_weight(self) -> None:
        """Bypass is disabled when LLM weight is zero."""
        quotas = QuotasConfig(
            arxiv_per_category_max=2,
            per_source_max=100,
            llm_bypass_threshold=0.70,
        )
        quota_filter = QuotaFilter(
            run_id="test",
            quotas_config=quotas,
            llm_relevance_weight=0.0,
        )

        stories = [
            self._make_arxiv_scored("s1", "cs.AI", 30.0, 0.0),
            self._make_arxiv_scored("s2", "cs.AI", 25.0, 0.0),
            self._make_arxiv_scored("s3", "cs.AI", 20.0, 0.0),
        ]

        kept, dropped = quota_filter.apply_quotas(stories)

        assert len(kept) == 2
        assert len(dropped) == 1


class TestPureFunction:
    """Tests for pure function API."""

    def test_apply_quotas_pure(self) -> None:
        """Pure function applies quotas correctly."""
        stories = [
            _make_scored_story(_make_story(story_id=f"s{i}", kind="paper"), 10 - i)
            for i in range(10)
        ]

        sections, dropped = apply_quotas_pure(
            scored_stories=stories,
            quotas_config=QuotasConfig(
                top5_max=3,
                papers_max=0,
                radar_max=2,
                per_source_max=100,
            ),
        )

        assert len(sections[StorySection.TOP5]) == 3
        assert len(sections[StorySection.RADAR]) <= 2
