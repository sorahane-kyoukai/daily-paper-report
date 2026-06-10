"""Tests for application settings."""

from pytest import MonkeyPatch

from src.settings.app import AppSettings


def test_empty_optional_env_values_are_ignored(monkeypatch: MonkeyPatch) -> None:
    """GitHub Actions passes missing secrets as empty strings."""
    monkeypatch.setenv("OPENAI_MAX_TOKENS", "")
    monkeypatch.setenv("OPENAI_MODEL", "")

    settings = AppSettings(_env_file=None)

    assert settings.openai_max_tokens is None
    assert settings.openai_model is None
