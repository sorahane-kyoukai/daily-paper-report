"""DeepSeek V4 Flash chat-completions client."""

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

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
CONTEXT_LIMIT_TOKENS = 1_000_000
INPUT_BUDGET_TOKENS = 900_000
MAX_INPUT_CHARS = 1_800_000
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0
_RETRYABLE = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class DeepSeekUsage:
    """Token accounting returned by DeepSeek."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0


class DeepSeekClient:
    """Minimal, observable client dedicated to ``deepseek-v4-flash``."""

    def __init__(
        self,
        api_key: str,
        model: str = DEEPSEEK_MODEL,
        max_tokens: int = 8192,
    ) -> None:
        if model != DEEPSEEK_MODEL:
            raise ValueError(f"model must be {DEEPSEEK_MODEL}")
        self._api_key = api_key
        self.model = model
        self._max_tokens = max_tokens
        self.last_usage = DeepSeekUsage()
        self._log = logger.bind(component="llm", subcomponent="deepseek")

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        """Generate a JSON response in non-thinking mode.

        DeepSeek documents JSON mode for non-thinking requests. All callers use
        object-shaped JSON prompts so malformed provider prose can be rejected.
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
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }
        response = self._request_with_retries(body)
        return self._parse_response(response)

    def _request_with_retries(self, body: dict[str, object]) -> httpx.Response:
        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
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
                    raise LlmApiError(f"DeepSeek API request failed: {exc}") from exc
                self._sleep_before_retry(attempt, None)
                continue

            if response.status_code == HTTPStatus.OK:
                return response
            if response.status_code not in _RETRYABLE or attempt >= _MAX_RETRIES:
                raise LlmApiError(
                    f"DeepSeek API returned {response.status_code}",
                    status_code=response.status_code,
                )
            self._sleep_before_retry(attempt, response.headers.get("Retry-After"))
        raise LlmApiError("DeepSeek retries exhausted")

    def _sleep_before_retry(self, attempt: int, retry_after: str | None) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = _RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # noqa: S311
        delay = min(delay, 120.0)
        self._log.warning(
            "deepseek_retry", attempt=attempt + 1, retry_delay=round(delay, 2)
        )
        time.sleep(delay)

    def _parse_response(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError as exc:
            raise LlmApiError("DeepSeek API returned invalid JSON") from exc
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmApiError("DeepSeek API response has no choices")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LlmApiError("DeepSeek API response has empty content")
        usage = data.get("usage", {})
        if isinstance(usage, dict):
            self.last_usage = DeepSeekUsage(
                prompt_tokens=_as_int(usage.get("prompt_tokens")),
                completion_tokens=_as_int(usage.get("completion_tokens")),
                total_tokens=_as_int(usage.get("total_tokens")),
                prompt_cache_hit_tokens=_as_int(
                    usage.get("prompt_cache_hit_tokens")
                ),
                prompt_cache_miss_tokens=_as_int(
                    usage.get("prompt_cache_miss_tokens")
                ),
            )
            self._log.info("deepseek_usage", **self.last_usage.__dict__)
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
