"""Tests for the OpenAI-compatible client factory."""

import pytest

from src.features.llm.errors import LlmAuthError
from src.features.llm.factory import create_llm_client
from src.features.llm.openai_client import OpenAICompatibleClient
from src.features.llm.protocols import LlmClient


def test_factory_creates_default_client() -> None:
    client = create_llm_client(api_key="test-key")
    assert isinstance(client, OpenAICompatibleClient)
    assert isinstance(client, LlmClient)
    assert client.model == "z-ai/glm-5.3-flash"


def test_factory_requires_key() -> None:
    with pytest.raises(LlmAuthError, match="LLM_API_KEY"):
        create_llm_client(api_key=None)


def test_factory_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model must be"):
        create_llm_client(api_key="test-key", model="")


def test_factory_passes_base_url() -> None:
    client = create_llm_client(
        api_key="test-key",
        model="z-ai/glm-5.3-flash",
        base_url="https://openrouter.ai/api/v1",
    )
    assert client.model == "z-ai/glm-5.3-flash"
