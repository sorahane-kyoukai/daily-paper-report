"""Factory for creating LLM clients with appropriate authentication."""

from __future__ import annotations

import structlog

from src.features.llm.errors import LlmAuthError
from src.features.llm.protocols import LlmClient


logger = structlog.get_logger()


def create_llm_client(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    refresh_token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    model: str = "gemini-2.5-flash",
    openai_api_key: str | None = None,
    openai_base_url: str | None = None,
    openai_model: str | None = None,
    openai_reasoning_effort: str | None = None,
    openai_thinking_type: str | None = None,
    openai_max_tokens: int | None = None,
) -> LlmClient:
    """Create an LLM client using the best available credentials.

    Provider selection:
    - ``gemini``: Gemini API key or CodeAssist OAuth.
    - ``openai``: OpenAI-compatible chat completions API.
    - ``deepseek``: OpenAI-compatible DeepSeek defaults.
    - ``auto``/unset: OpenAI-compatible if only OpenAI credentials are present,
      otherwise Gemini.

    Args:
        provider: LLM provider selector.
        api_key: Gemini API key. Preferred when available.
        refresh_token: Google OAuth refresh token for CodeAssist.
        client_id: OAuth client ID (required with refresh_token).
        client_secret: OAuth client secret (required with refresh_token).
        model: Gemini model identifier.
        openai_api_key: API key for OpenAI-compatible providers.
        openai_base_url: Base URL for OpenAI-compatible providers.
        openai_model: Model identifier for OpenAI-compatible providers.
        openai_reasoning_effort: Optional reasoning effort.
        openai_thinking_type: Optional thinking mode.
        openai_max_tokens: Optional response token limit.

    Returns:
        An LlmClient implementation ready for use.

    Raises:
        LlmAuthError: If no valid credentials are provided.
    """
    log = logger.bind(component="llm", subcomponent="factory")

    normalized_provider = _resolve_provider(
        provider=provider,
        gemini_api_key=api_key,
        gemini_refresh_token=refresh_token,
        openai_api_key=openai_api_key,
    )

    if normalized_provider in {"openai", "deepseek"}:
        return _create_openai_compatible_client(
            provider=normalized_provider,
            api_key=openai_api_key,
            base_url=openai_base_url,
            model=openai_model,
            reasoning_effort=openai_reasoning_effort,
            thinking_type=openai_thinking_type,
            max_tokens=openai_max_tokens,
            log=log,
        )

    if normalized_provider != "gemini":
        msg = f"Unsupported LLM provider: {provider}"
        raise LlmAuthError(msg)

    if api_key:
        from src.features.llm.gemini_client import GeminiApiKeyClient

        log.info("llm_client_created", provider="gemini", auth_method="api_key")
        return GeminiApiKeyClient(api_key=api_key, model=model)

    if refresh_token:
        from src.features.llm.auth import refresh_access_token
        from src.features.llm.client import GeminiCodeAssistClient

        access_token = refresh_access_token(
            refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )

        def _token_refresher() -> str:
            return refresh_access_token(
                refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )

        log.info("llm_client_created", provider="gemini", auth_method="oauth")
        return GeminiCodeAssistClient(
            access_token=access_token,
            model=model,
            token_refresher=_token_refresher,
        )

    msg = "No LLM credentials configured (need Gemini or OpenAI-compatible credentials)"
    raise LlmAuthError(msg)


def _resolve_provider(
    *,
    provider: str | None,
    gemini_api_key: str | None,
    gemini_refresh_token: str | None,
    openai_api_key: str | None,
) -> str:
    """Resolve the configured LLM provider."""
    value = (provider or "auto").strip().lower().replace("_", "-")
    aliases = {
        "openai-compatible": "openai",
        "openai-compatible-chat": "openai",
    }
    value = aliases.get(value, value)

    if value == "auto":
        if openai_api_key and not (gemini_api_key or gemini_refresh_token):
            return "openai"
        return "gemini"

    return value


def _create_openai_compatible_client(
    *,
    provider: str,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    reasoning_effort: str | None,
    thinking_type: str | None,
    max_tokens: int | None,
    log: structlog.typing.FilteringBoundLogger,
) -> LlmClient:
    """Create an OpenAI-compatible client."""
    if not api_key:
        msg = "No OpenAI-compatible credentials configured (need OPENAI_API_KEY)"
        raise LlmAuthError(msg)

    from src.features.llm.openai_compatible_client import OpenAiCompatibleClient

    effective_base_url = base_url or (
        "https://api.deepseek.com"
        if provider == "deepseek"
        else "https://api.openai.com/v1"
    )
    effective_model = model or (
        "deepseek-v4-pro" if provider == "deepseek" else "gpt-4o-mini"
    )

    log.info(
        "llm_client_created",
        provider=provider,
        auth_method="api_key",
        base_url=effective_base_url,
        model=effective_model,
    )
    return OpenAiCompatibleClient(
        api_key=api_key,
        base_url=effective_base_url,
        model=effective_model,
        reasoning_effort=reasoning_effort,
        thinking_type=thinking_type,
        max_tokens=max_tokens,
    )
