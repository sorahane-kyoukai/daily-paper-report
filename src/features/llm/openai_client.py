"""OpenAI-compatible chat-completions client (OpenRouter by default)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from http import HTTPStatus

import httpx
import structlog

from src.features.llm.errors import LlmApiError


logger = structlog.get_logger()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"
CONTEXT_LIMIT_TOKENS = 1_000_000
INPUT_BUDGET_TOKENS = 900_000
MAX_INPUT_CHARS = 1_800_000
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0
_RETRYABLE = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LlmUsage:
    """Token accounting returned by the provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0


class OpenAICompatibleClient:
    """Minimal, observable client for OpenAI-compatible chat endpoints.

    Targets OpenRouter by default. JSON mode (``response_format``) is always
    requested; reasoning content is excluded from responses so callers only
    ever parse the JSON payload.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 8192,
        base_url: str = OPENROUTER_BASE_URL,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty model id")
        self._api_key = api_key
        self.model = model
        self._max_tokens = max_tokens
        self._base_url = base_url.rstrip("/")
        self.last_usage = LlmUsage()
        self._log = logger.bind(component="llm", subcomponent="openai-compat")

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        """Generate a JSON response.

        Callers use object-shaped JSON prompts so malformed provider prose
        can be rejected; JSON mode plus the processors' fence-tolerant
        parsing handles providers that wrap or decorate output.
        """
        if len(prompt) > MAX_INPUT_CHARS:
            raise LlmApiError(
                f"Prompt exceeds the safe 1M-context budget ({len(prompt)} chars)"
            )
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }
        if "openrouter.ai" in self._base_url:
            # Reasoning is mandatory for some OpenRouter models; only request
            # that its text stay out of the response content.
            body["reasoning"] = {"exclude": True}
        response = self._request_with_retries(body)
        return self._parse_response(response)

    def _request_with_retries(self, body: dict[str, object]) -> httpx.Response:
        url = f"{self._base_url}/chat/completions"
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = httpx.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=httpx.Timeout(600.0, connect=30.0),
                )
            except httpx.HTTPError as exc:
                if attempt >= _MAX_RETRIES:
                    raise LlmApiError(f"LLM API request failed: {exc}") from exc
                self._sleep_before_retry(attempt, None)
                continue

            if response.status_code == HTTPStatus.OK:
                return response
            if response.status_code not in _RETRYABLE or attempt >= _MAX_RETRIES:
                raise LlmApiError(
                    f"LLM API returned {response.status_code}",
                    status_code=response.status_code,
                )
            self._sleep_before_retry(attempt, response.headers.get("Retry-After"))
        raise LlmApiError("LLM retries exhausted")

    def _sleep_before_retry(self, attempt: int, retry_after: str | None) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = _RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # noqa: S311
        delay = min(delay, 120.0)
        self._log.warning("llm_retry", attempt=attempt + 1, retry_delay=round(delay, 2))
        time.sleep(delay)

    def _parse_response(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError as exc:
            raise LlmApiError("LLM API returned invalid JSON") from exc
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            raise LlmApiError(f"LLM API error: {error['message']}")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmApiError("LLM API response has no choices")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LlmApiError("LLM API response has empty content")
        usage = data.get("usage", {})
        if isinstance(usage, dict):
            details = usage.get("prompt_tokens_details")
            cached = details.get("cached_tokens") if isinstance(details, dict) else None
            prompt_tokens = _as_int(usage.get("prompt_tokens"))
            cache_hit = _as_int(cached)
            self.last_usage = LlmUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=_as_int(usage.get("completion_tokens")),
                total_tokens=_as_int(usage.get("total_tokens")),
                prompt_cache_hit_tokens=cache_hit,
                prompt_cache_miss_tokens=max(0, prompt_tokens - cache_hit),
            )
            self._log.info("llm_usage", **self.last_usage.__dict__)
        return content


def _as_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None
