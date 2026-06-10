"""Standard Gemini API client using API key authentication."""

import random
import time
from http import HTTPStatus

import httpx
import structlog

from src.features.llm.errors import LlmApiError


logger = structlog.get_logger()

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

_MIN_REQUEST_INTERVAL = 5.0
_MAX_RETRIES = 8
_RETRY_BASE_DELAY = 5.0
_RETRYABLE_STATUS_CODES = {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}


class GeminiApiKeyClient:
    """Client for the standard Gemini API using API key authentication.

    Uses the ``generativelanguage.googleapis.com`` endpoint with an
    ``x-goog-api-key`` header. API keys do not expire, making this
    more reliable than OAuth for automated pipelines.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
    ) -> None:
        """Initialize the client.

        Args:
            api_key: Gemini API key (never expires).
            model: Gemini model identifier.
        """
        self._api_key = api_key
        self.model = model
        self._last_request_time: float = 0.0
        self._log = logger.bind(component="llm", subcomponent="gemini_api_key")

    def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        """Send a generate content request to the Gemini API.

        Retries with exponential backoff on 429/503 responses.

        Args:
            prompt: User prompt text.
            system_instruction: Optional system instruction.

        Returns:
            Generated text from the model response.

        Raises:
            LlmApiError: If the API call fails after all retries.
        """
        url = f"{_BASE_URL}/{self.model}:generateContent"

        request_body: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        if system_instruction:
            request_body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        last_exc: LlmApiError | None = None

        for attempt in range(_MAX_RETRIES + 1):
            self._rate_limit()

            try:
                response = httpx.post(
                    url,
                    headers={
                        "x-goog-api-key": self._api_key,
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=60.0,
                )
            except httpx.HTTPError as exc:
                msg = f"Gemini API request failed: {exc}"
                raise LlmApiError(msg) from exc

            if response.status_code == HTTPStatus.OK:
                break

            status = HTTPStatus(response.status_code)
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # noqa: S311
                self._log.warning(
                    "gemini_retryable_error",
                    status=response.status_code,
                    attempt=attempt + 1,
                    retry_delay=round(delay, 1),
                )
                time.sleep(delay)
                last_exc = LlmApiError(
                    f"Gemini API returned {response.status_code}",
                    status_code=response.status_code,
                )
                continue

            msg = f"Gemini API returned {response.status_code}"
            raise LlmApiError(msg, status_code=response.status_code)
        else:
            raise last_exc or LlmApiError("All retries exhausted")

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            msg = "No candidates in Gemini API response"
            raise LlmApiError(msg)

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            msg = "No parts in first candidate"
            raise LlmApiError(msg)

        text: str = parts[0].get("text", "")
        if not text:
            msg = "Empty text in response"
            raise LlmApiError(msg)

        return text
