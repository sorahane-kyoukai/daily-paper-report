"""Gemini CodeAssist API client."""

import random
import time
import uuid
from collections.abc import Callable
from http import HTTPStatus

import httpx
import structlog

from src.features.llm.errors import LlmApiError


logger = structlog.get_logger()

_GENERATE_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
_CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"

_MIN_REQUEST_INTERVAL = 5.0  # seconds between requests (increased for rate limit)
_MAX_RETRIES = 8  # increased retries
_RETRY_BASE_DELAY = 5.0  # seconds (increased base delay)
_RETRYABLE_STATUS_CODES = {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}
_AUTH_ERROR_STATUS_CODES = {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}


class GeminiCodeAssistClient:
    """Client for the Gemini CodeAssist API.

    Handles request formatting, rate limiting, and response parsing
    for the CodeAssist generateContent endpoint.

    Attributes:
        model: Gemini model identifier to use.
    """

    def __init__(
        self,
        access_token: str,
        model: str = "gemini-2.5-flash",
        token_refresher: Callable[[], str] | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            access_token: Google OAuth access token.
            model: Gemini model identifier.
            token_refresher: Optional callable that returns a fresh access
                token. Called once on 401/403 to attempt recovery.
        """
        self._access_token = access_token
        self.model = model
        self._token_refresher = token_refresher
        self._project: str | None = None
        self._last_request_time: float = 0.0
        self._log = logger.bind(component="llm", subcomponent="client")

    def _refresh_token_once(self) -> bool:
        """Attempt a single token refresh via the configured refresher.

        Returns:
            True if the token was refreshed, False if no refresher available.

        Raises:
            LlmApiError: If the refresh itself fails.
        """
        if self._token_refresher is None:
            return False

        self._log.info("oauth_token_auto_refresh_attempt")
        try:
            self._access_token = self._token_refresher()
        except Exception as exc:
            self._log.warning("oauth_token_auto_refresh_failed", error=str(exc))
            msg = f"Token auto-refresh failed: {exc}"
            raise LlmApiError(msg) from exc

        # Invalidate cached project so it re-resolves with the new token.
        self._project = None
        self._log.info("oauth_token_auto_refreshed")
        return True

    def _get_project(self) -> str:
        """Obtain or return cached project identifier from CodeAssist.

        On 401/403 from CodeAssist, attempts a single token refresh
        before raising.

        Returns:
            Project string for API requests.

        Raises:
            LlmApiError: If project lookup fails.
        """
        if self._project is not None:
            return self._project

        response = self._project_request()

        if (
            HTTPStatus(response.status_code) in _AUTH_ERROR_STATUS_CODES
            and self._refresh_token_once()
        ):
            response = self._project_request()

        if response.status_code != HTTPStatus.OK:
            msg = f"CodeAssist project lookup returned {response.status_code}"
            raise LlmApiError(msg, status_code=response.status_code)

        data = response.json()
        project: str = data.get("cloudaicompanionProject", "") or data.get(
            "project", ""
        )
        if not project:
            msg = "No project in CodeAssist response"
            raise LlmApiError(msg)

        self._project = project
        self._log.info("code_assist_project_resolved", project=project)
        return project

    def _project_request(self) -> httpx.Response:
        """Send the project lookup HTTP request.

        Returns:
            HTTP response from CodeAssist.

        Raises:
            LlmApiError: On network errors.
        """
        try:
            return httpx.post(
                _CODE_ASSIST_ENDPOINT,
                headers={"Authorization": f"Bearer {self._access_token}"},
                json={},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            msg = f"CodeAssist project lookup failed: {exc}"
            raise LlmApiError(msg) from exc

    def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    def _build_request_body(
        self,
        prompt: str,
        system_instruction: str | None,
        project: str,
    ) -> dict[str, object]:
        """Build the CodeAssist API request body."""
        request_inner: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        if system_instruction:
            request_inner["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
        return {
            "model": self.model,
            "project": project,
            "user_prompt_id": str(uuid.uuid4()),
            "request": request_inner,
        }

    def _send_generate_request(self, request_body: dict[str, object]) -> httpx.Response:
        """Send a single generate-content HTTP request.

        Raises:
            LlmApiError: On network errors.
        """
        try:
            return httpx.post(
                _GENERATE_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            msg = f"GenerateContent request failed: {exc}"
            raise LlmApiError(msg) from exc

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        """Send a generate content request to the CodeAssist API.

        Retries with exponential backoff on 429/503 responses.
        On 401/403, attempts a single token refresh before failing.

        Args:
            prompt: User prompt text.
            system_instruction: Optional system instruction.

        Returns:
            Generated text from the model response.

        Raises:
            LlmApiError: If the API call fails after all retries.
        """
        project = self._get_project()
        request_body = self._build_request_body(prompt, system_instruction, project)

        response = self._retry_loop(request_body)

        return self._extract_text(response)

    def _retry_loop(self, request_body: dict[str, object]) -> httpx.Response:
        """Execute the retry loop for generate requests.

        Returns:
            Successful HTTP response.

        Raises:
            LlmApiError: If the request fails after all retries.
        """
        last_exc: LlmApiError | None = None
        auth_retried = False

        for attempt in range(_MAX_RETRIES + 1):
            self._rate_limit()
            response = self._send_generate_request(request_body)

            if response.status_code == HTTPStatus.OK:
                return response

            status = HTTPStatus(response.status_code)

            if status in _AUTH_ERROR_STATUS_CODES and not auth_retried:
                auth_retried = True
                if self._refresh_token_once():
                    project = self._get_project()
                    request_body["project"] = project
                    continue

            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # noqa: S311
                self._log.warning(
                    "llm_retryable_error",
                    status=response.status_code,
                    attempt=attempt + 1,
                    retry_delay=round(delay, 1),
                )
                time.sleep(delay)
                last_exc = LlmApiError(
                    f"GenerateContent returned {response.status_code}",
                    status_code=response.status_code,
                )
                continue

            msg = f"GenerateContent returned {response.status_code}"
            raise LlmApiError(msg, status_code=response.status_code)

        raise last_exc or LlmApiError("All retries exhausted")

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        """Extract generated text from the API response.

        Raises:
            LlmApiError: If the response is missing expected fields.
        """
        data = response.json()
        # Response may be nested under "response" key or flat
        inner = data.get("response", data)
        candidates = inner.get("candidates", [])
        if not candidates:
            msg = "No candidates in GenerateContent response"
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
