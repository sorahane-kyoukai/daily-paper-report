"""Google OAuth token refresh for Gemini CodeAssist API."""

import os
from http import HTTPStatus

import httpx
import structlog

from src.features.llm.errors import LlmAuthError


logger = structlog.get_logger()

_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105

# OAuth client credentials read from environment variables.
# Obtain these from the Gemini CLI OAuth flow or set them in .env.
_CLIENT_ID = os.environ.get("GEMINI_OAUTH_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("GEMINI_OAUTH_CLIENT_SECRET", "")  # noqa: S105


def refresh_access_token(
    refresh_token: str,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str:
    """Exchange a refresh token for a new Google OAuth access token.

    Args:
        refresh_token: Long-lived refresh token from Gemini CLI OAuth flow.
        client_id: OAuth client ID. Falls back to GEMINI_OAUTH_CLIENT_ID env var.
        client_secret: OAuth client secret. Falls back to GEMINI_OAUTH_CLIENT_SECRET env var.

    Returns:
        Fresh access token string.

    Raises:
        LlmAuthError: If the token refresh request fails.
    """
    log = logger.bind(component="llm", subcomponent="auth")

    effective_client_id = client_id or _CLIENT_ID
    effective_client_secret = client_secret or _CLIENT_SECRET

    try:
        response = httpx.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id": effective_client_id,
                "client_secret": effective_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        log.warning("oauth_token_refresh_network_error", error=str(exc))
        msg = f"Network error during token refresh: {exc}"
        raise LlmAuthError(msg) from exc

    if response.status_code != HTTPStatus.OK:
        log.warning(
            "oauth_token_refresh_failed",
            status_code=response.status_code,
        )
        msg = f"Token refresh failed with status {response.status_code}"
        raise LlmAuthError(msg)

    data = response.json()
    access_token: str | None = data.get("access_token")
    if not access_token:
        msg = "No access_token in refresh response"
        raise LlmAuthError(msg)

    log.info("oauth_token_refreshed")
    return access_token
