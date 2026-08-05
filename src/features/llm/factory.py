"""Construct the single supported DeepSeek client."""

from src.features.llm.deepseek_client import DeepSeekClient
from src.features.llm.errors import LlmAuthError
from src.features.llm.protocols import LlmClient


def create_llm_client(
    *,
    api_key: str | None,
    model: str = "deepseek-v4-flash",
    max_tokens: int = 8192,
) -> LlmClient:
    """Create the DeepSeek client or fail closed when its key is absent."""
    if not api_key:
        raise LlmAuthError("DEEPSEEK_API_KEY is required")
    if model != "deepseek-v4-flash":
        raise LlmAuthError("Only deepseek-v4-flash is supported")
    return DeepSeekClient(api_key=api_key, model=model, max_tokens=max_tokens)
