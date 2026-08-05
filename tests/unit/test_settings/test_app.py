"""Tests for application settings."""

from pytest import MonkeyPatch

from src.settings.app import AppSettings


def test_empty_optional_env_values_are_ignored(monkeypatch: MonkeyPatch) -> None:
    """An empty optional key should be treated as absent."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")

    settings = AppSettings(_env_file=None)

    assert settings.deepseek_api_key is None
    assert settings.deepseek_model == "deepseek-v4-flash"
