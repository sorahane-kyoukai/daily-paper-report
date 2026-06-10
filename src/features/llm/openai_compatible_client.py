"""OpenAI-compatible chat completions client."""

import random
import time
from http import HTTPStatus

import httpx
import structlog

from src.features.llm.errors import LlmApiError


logger = structlog.get_logger()

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MIN_REQUEST_INTERVAL = 1.0
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0
_RETRYABLE_STATUS_CODES = {
    HTTPStatus.TOO_MANY_REQUESTS,
    HTTPStatus.INTERNAL_SERVER_ERROR,
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT,
}


class OpenAiCompatibleClient:
    """Client for OpenAI-compatible chat completions APIs."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        reasoning_effort: str | None = None,
        thinking_type: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            api_key: API key for the OpenAI-compatible provider.
            model: Chat completions model identifier.
            base_url: Provider base URL. The client appends /chat/completions.
            reasoning_effort: Optional provider-specific reasoning effort.
            thinking_type: Optional provider-specific thinking mode.
            max_tokens: Optional response token limit.
        """
        self._api_key = api_key
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._reasoning_effort = reasoning_effort
        self._thinking_type = thinking_type
        self._max_tokens = max_tokens
        self._last_request_time: float = 0.0
        self._log = logger.bind(component="llm", subcomponent="openai_compatible")

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
        """Send a chat completions request.

        Args:
            prompt: User prompt text.
            system_instruction: Optional system instruction.

        Returns:
            Generated text from the model response.

        Raises:
            LlmApiError: If the API call fails after all retries.
        """
        request_body = self._build_request_body(prompt, system_instruction)
        response = self._retry_loop(request_body)
        return self._extract_text(response)

    def _build_request_body(
        self,
        prompt: str,
        system_instruction: str | None,
    ) -> dict[str, object]:
        """Build a chat completions request body."""
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        request_body: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if self._reasoning_effort:
            request_body["reasoning_effort"] = self._reasoning_effort
        if self._thinking_type and self._thinking_type.lower() not in {
            "0",
            "disabled",
            "false",
            "none",
            "off",
        }:
            request_body["thinking"] = {"type": self._thinking_type}
        if self._max_tokens is not None:
            request_body["max_tokens"] = self._max_tokens
        return request_body

    def _retry_loop(self, request_body: dict[str, object]) -> httpx.Response:
        """Execute the retry loop for chat completion requests."""
        url = f"{self._base_url}/chat/completions"
        last_exc: LlmApiError | None = None

        for attempt in range(_MAX_RETRIES + 1):
            self._rate_limit()
            response = self._send_request(url, request_body)

            if response.status_code == HTTPStatus.OK:
                return response

            status = HTTPStatus(response.status_code)
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # noqa: S311
                self._log.warning(
                    "openai_compatible_retryable_error",
                    status=response.status_code,
                    attempt=attempt + 1,
                    retry_delay=round(delay, 1),
                )
                time.sleep(delay)
                last_exc = LlmApiError(
                    f"OpenAI-compatible API returned {response.status_code}",
                    status_code=response.status_code,
                )
                continue

            msg = f"OpenAI-compatible API returned {response.status_code}"
            raise LlmApiError(msg, status_code=response.status_code)

        raise last_exc or LlmApiError("All retries exhausted")

    def _send_request(
        self,
        url: str,
        request_body: dict[str, object],
    ) -> httpx.Response:
        """Send a single HTTP request."""
        try:
            return httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=90.0,
            )
        except httpx.HTTPError as exc:
            msg = f"OpenAI-compatible API request failed: {exc}"
            raise LlmApiError(msg) from exc

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        """Extract generated text from an OpenAI-compatible response."""
        try:
            data = response.json()
        except ValueError as exc:
            msg = "OpenAI-compatible API returned invalid JSON"
            raise LlmApiError(msg, status_code=response.status_code) from exc

        choices = data.get("choices", [])
        if not choices:
            msg = "No choices in OpenAI-compatible API response"
            raise LlmApiError(msg, status_code=response.status_code)

        message = choices[0].get("message", {})
        content = message.get("content", "")
        text = _content_to_text(content)
        if not text:
            msg = "Empty content in OpenAI-compatible API response"
            raise LlmApiError(msg, status_code=response.status_code)

        return text


def _content_to_text(content: object) -> str:
    """Normalize OpenAI chat message content to plain text."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    return ""
