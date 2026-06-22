"""Tests for CLI LLM settings wiring."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.cli.digest import _create_configured_llm_client


def test_deepseek_provider_prefers_deepseek_key_over_openai_key() -> None:
    """DeepSeek provider should not send an OpenAI key to DeepSeek."""
    settings = SimpleNamespace(
        llm_provider="deepseek",
        gemini_api_key=None,
        gemini_refresh_token=None,
        gemini_oauth_client_id=None,
        gemini_oauth_client_secret=None,
        openai_api_key="openai-key",
        deepseek_api_key="deepseek-key",
        openai_base_url=None,
        openai_model=None,
        openai_reasoning_effort=None,
        openai_thinking_type=None,
        openai_max_tokens=None,
    )

    with patch("src.features.llm.factory.create_llm_client") as create_client:
        create_client.return_value = MagicMock()

        _create_configured_llm_client(settings)

    assert create_client.call_args.kwargs["provider"] == "deepseek"
    assert create_client.call_args.kwargs["openai_api_key"] == "deepseek-key"
