"""Tests for CLI LLM settings wiring."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.cli.digest import _collect_ranker_story_dicts, _create_configured_llm_client
from src.features.config.schemas.base import LinkType
from src.linker.models import Story, StoryLink
from src.ranker.models import RankerOutput, RankerResult


def test_cli_configures_translation_model() -> None:
    """The CLI should wire the configured LLM settings for translation."""
    settings = SimpleNamespace(
        llm_api_key="llm-key",
        llm_model="z-ai/glm-5.3-flash",
        llm_scoring_model="z-ai/glm-5.3-flash",
        llm_max_tokens=8192,
        llm_base_url="https://openrouter.ai/api/v1",
    )

    with patch("src.features.llm.factory.create_llm_client") as create_client:
        create_client.return_value = MagicMock()

        _create_configured_llm_client(settings)

    assert create_client.call_args.kwargs == {
        "api_key": "llm-key",
        "model": "z-ai/glm-5.3-flash",
        "max_tokens": 8192,
        "base_url": "https://openrouter.ai/api/v1",
    }


def test_cli_configures_scoring_model() -> None:
    """Scoring/report metadata should use the dedicated scoring model."""
    settings = SimpleNamespace(
        llm_api_key="llm-key",
        llm_model="z-ai/glm-5.3-flash",
        llm_scoring_model="z-ai/glm-5.3-flash",
        llm_max_tokens=8192,
        llm_base_url="https://openrouter.ai/api/v1",
    )

    with patch("src.features.llm.factory.create_llm_client") as create_client:
        create_client.return_value = MagicMock()

        _create_configured_llm_client(settings, model=settings.llm_scoring_model)

    assert create_client.call_args.kwargs == {
        "api_key": "llm-key",
        "model": "z-ai/glm-5.3-flash",
        "max_tokens": 8192,
        "base_url": "https://openrouter.ai/api/v1",
    }


def test_translation_candidates_include_all_visible_story_types() -> None:
    """Daily translation should cover blog/news cards, not only papers."""

    def story(story_id: str, link_type: LinkType) -> Story:
        return Story(
            story_id=story_id,
            title=f"Story {story_id}",
            primary_link=StoryLink(
                url=f"https://example.com/{story_id}",
                link_type=link_type,
                source_id="source",
                tier=1,
                title=f"Story {story_id}",
            ),
            links=[
                StoryLink(
                    url=f"https://example.com/{story_id}",
                    link_type=link_type,
                    source_id="source",
                    tier=1,
                    title=f"Story {story_id}",
                )
            ],
        )

    blog_story = story("blog-story", LinkType.BLOG)
    paper_story = story("paper-story", LinkType.ARXIV)
    radar_story = story("radar-story", LinkType.OFFICIAL)
    model_story = story("model-story", LinkType.HUGGINGFACE)

    ranker_result = RankerResult(
        output=RankerOutput(
            top5=[blog_story, paper_story],
            papers=[paper_story],
            radar=[radar_story],
            model_releases_by_entity={"openai": [model_story]},
        ),
        stories_in=4,
        stories_out=4,
        dropped_total=0,
    )

    candidates = _collect_ranker_story_dicts(ranker_result)

    assert [candidate["story_id"] for candidate in candidates] == [
        "blog-story",
        "paper-story",
        "radar-story",
        "model-story",
    ]
