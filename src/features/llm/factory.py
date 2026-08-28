"""Construct the OpenAI-compatible LLM client (OpenRouter by default)."""

from src.features.llm.errors import LlmAuthError
from src.features.llm.openai_client import (
    DEFAULT_MODEL,
    OPENROUTER_BASE_URL,
    OpenAICompatibleClient,
)
from src.features.llm.protocols import LlmClient


def create_llm_client(
    *,
    api_key: str | None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8192,
    base_url: str = OPENROUTER_BASE_URL,
) -> LlmClient:
    """Create an LLM client or fail closed when its key is absent."""
    if not api_key:
        raise LlmAuthError("LLM_API_KEY is required")
    return OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        base_url=base_url,
    )
