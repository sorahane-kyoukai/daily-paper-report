"""Tests for application settings."""

from pytest import MonkeyPatch

from src.settings.app import AppSettings


def test_empty_optional_env_values_are_ignored(monkeypatch: MonkeyPatch) -> None:
    """An empty optional key should be treated as absent."""
    monkeypatch.setenv("LLM_API_KEY", "")

    settings = AppSettings(_env_file=None)

    assert settings.llm_api_key is None
    assert settings.llm_model == "z-ai/glm-5.3-flash"
    assert settings.llm_scoring_model == "z-ai/glm-5.3-flash"
    assert settings.llm_base_url == "https://openrouter.ai/api/v1"


def test_legacy_deepseek_key_alias(monkeypatch: MonkeyPatch) -> None:
    """The legacy DEEPSEEK_API_KEY name still feeds the LLM key."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "legacy-key")

    settings = AppSettings(_env_file=None)

    assert settings.llm_api_key == "legacy-key"
