"""Tests for the DeepSeek-only client factory."""

import pytest

from src.features.llm.deepseek_client import DeepSeekClient
from src.features.llm.errors import LlmAuthError
from src.features.llm.factory import create_llm_client
from src.features.llm.protocols import LlmClient


def test_factory_creates_v4_flash_client() -> None:
    client = create_llm_client(api_key="test-key")
    assert isinstance(client, DeepSeekClient)
    assert isinstance(client, LlmClient)
    assert client.model == "deepseek-v4-flash"


def test_factory_requires_key() -> None:
    with pytest.raises(LlmAuthError, match="DEEPSEEK_API_KEY"):
        create_llm_client(api_key=None)


def test_factory_rejects_other_models() -> None:
    with pytest.raises(LlmAuthError, match="deepseek-v4-flash"):
        create_llm_client(api_key="test-key", model="another-model")
