"""Unit tests for LLM OAuth token refresh."""

from unittest.mock import MagicMock, patch

import pytest

from src.features.llm.auth import refresh_access_token
from src.features.llm.errors import LlmAuthError


class TestRefreshAccessToken:
    """Tests for refresh_access_token function."""

    @patch("src.features.llm.auth.httpx.post")
    def test_success_returns_access_token(self, mock_post: MagicMock) -> None:
        """Should return access token on successful refresh."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ya29.test-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        token = refresh_access_token("1//test-refresh-token")

        assert token == "ya29.test-token"  # noqa: S105
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["data"]["grant_type"] == "refresh_token"
        assert call_kwargs[1]["data"]["refresh_token"] == "1//test-refresh-token"  # noqa: S105

    @patch("src.features.llm.auth.httpx.post")
    def test_http_error_raises_auth_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmAuthError on network failure."""
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(LlmAuthError, match="Network error"):
            refresh_access_token("1//test-refresh-token")

    @patch("src.features.llm.auth.httpx.post")
    def test_non_200_raises_auth_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmAuthError on non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        with pytest.raises(LlmAuthError, match="status 401"):
            refresh_access_token("1//test-refresh-token")

    @patch("src.features.llm.auth.httpx.post")
    def test_missing_access_token_raises_auth_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmAuthError when response has no access_token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token_type": "Bearer"}
        mock_post.return_value = mock_response

        with pytest.raises(LlmAuthError, match="No access_token"):
            refresh_access_token("1//test-refresh-token")

    @patch.dict(
        "os.environ",
        {
            "GEMINI_OAUTH_CLIENT_ID": "test-id.apps.googleusercontent.com",
            "GEMINI_OAUTH_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("src.features.llm.auth.httpx.post")
    def test_sends_correct_client_credentials(self, mock_post: MagicMock) -> None:
        """Should send configured client credentials from env vars."""
        # Reload module to pick up patched env vars
        import importlib

        import src.features.llm.auth as auth_mod

        importlib.reload(auth_mod)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "ya29.test"}
        mock_post.return_value = mock_response

        auth_mod.refresh_access_token("1//test-refresh-token")

        call_data = mock_post.call_args[1]["data"]
        assert call_data["client_id"] == "test-id.apps.googleusercontent.com"
        assert call_data["client_secret"] == "test-secret"  # noqa: S105
