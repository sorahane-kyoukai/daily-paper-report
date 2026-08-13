"""Construct DeepSeek clients for translation (flash) and scoring (pro)."""

from src.features.llm.deepseek_client import (
    DEEPSEEK_MODEL,
    DEEPSEEK_PRO_MODEL,
    DeepSeekClient,
)
from src.features.llm.errors import LlmAuthError
from src.features.llm.protocols import LlmClient


def create_llm_client(
    *,
    api_key: str | None,
    model: str = DEEPSEEK_MODEL,
    max_tokens: int = 8192,
    thinking: bool | None = None,
) -> LlmClient:
    """Create a DeepSeek client or fail closed when its key is absent.

    ``deepseek-v4-pro`` defaults to thinking mode; ``deepseek-v4-flash``
    defaults to non-thinking JSON mode. Pass ``thinking`` to override.
    """
    if not api_key:
        raise LlmAuthError("DEEPSEEK_API_KEY is required")
    if thinking is None:
        thinking = model == DEEPSEEK_PRO_MODEL
    return DeepSeekClient(
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        thinking=thinking,
    )
