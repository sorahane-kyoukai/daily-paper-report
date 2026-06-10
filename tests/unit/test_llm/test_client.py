"""Unit tests for Gemini CodeAssist API client."""

from unittest.mock import MagicMock, patch

import pytest

from src.features.llm.client import GeminiCodeAssistClient
from src.features.llm.errors import LlmApiError


def _make_client(
    access_token: str = "ya29.test-token",  # noqa: S107
    model: str = "gemini-3-pro-preview",
) -> GeminiCodeAssistClient:
    """Create a test client with pre-set project."""
    client = GeminiCodeAssistClient(access_token=access_token, model=model)
    client._project = "test-project"  # noqa: SLF001
    return client


class TestGenerateContent:
    """Tests for GeminiCodeAssistClient.generate_content."""

    @patch("src.features.llm.client.httpx.post")
    def test_success_returns_text(self, mock_post: MagicMock) -> None:
        """Should return text from model response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello world"}]}}]
        }
        mock_post.return_value = mock_response

        client = _make_client()
        result = client.generate_content("Say hello")

        assert result == "Hello world"

    @patch("src.features.llm.client.httpx.post")
    def test_sends_correct_request_format(self, mock_post: MagicMock) -> None:
        """Should send request in CodeAssist API format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response

        client = _make_client()
        client.generate_content("Test prompt", system_instruction="Be helpful")

        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"]
        assert body["model"] == "gemini-3-pro-preview"
        assert body["project"] == "test-project"
        assert "user_prompt_id" in body
        assert body["request"]["contents"][0]["parts"][0]["text"] == "Test prompt"
        assert "systemInstruction" in body["request"]

    @patch("src.features.llm.client.httpx.post")
    def test_non_200_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError on non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response

        client = _make_client()

        with pytest.raises(LlmApiError, match="400"):
            client.generate_content("Test")

    @patch("src.features.llm.client.httpx.post")
    def test_empty_candidates_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError when response has no candidates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"candidates": []}
        mock_post.return_value = mock_response

        client = _make_client()

        with pytest.raises(LlmApiError, match="No candidates"):
            client.generate_content("Test")

    @patch("src.features.llm.client.httpx.post")
    def test_network_error_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError on network failure."""
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")

        client = _make_client()

        with pytest.raises(LlmApiError, match="request failed"):
            client.generate_content("Test")

    @patch("src.features.llm.client.httpx.post")
    def test_no_system_instruction_omitted(self, mock_post: MagicMock) -> None:
        """Should omit systemInstruction when not provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response

        client = _make_client()
        client.generate_content("Test prompt")

        body = mock_post.call_args[1]["json"]
        assert "systemInstruction" not in body["request"]


class TestGetProject:
    """Tests for project resolution."""

    @patch("src.features.llm.client.httpx.post")
    def test_resolves_project_from_cloudai_field(self, mock_post: MagicMock) -> None:
        """Should resolve project from cloudaicompanionProject field."""
        project_response = MagicMock()
        project_response.status_code = 200
        project_response.json.return_value = {
            "cloudaicompanionProject": "rapid-elevator-abc",
            "currentTier": {"id": "standard-tier"},
        }

        generate_response = MagicMock()
        generate_response.status_code = 200
        generate_response.json.return_value = {
            "response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        }

        mock_post.side_effect = [project_response, generate_response]

        client = GeminiCodeAssistClient(access_token="ya29.test")  # noqa: S106
        result = client.generate_content("Test")

        assert result == "ok"
        assert mock_post.call_count == 2

    @patch("src.features.llm.client.httpx.post")
    def test_resolves_project_from_legacy_field(self, mock_post: MagicMock) -> None:
        """Should fall back to legacy project field."""
        project_response = MagicMock()
        project_response.status_code = 200
        project_response.json.return_value = {"project": "my-project-123"}

        generate_response = MagicMock()
        generate_response.status_code = 200
        generate_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }

        mock_post.side_effect = [project_response, generate_response]

        client = GeminiCodeAssistClient(access_token="ya29.test")  # noqa: S106
        result = client.generate_content("Test")

        assert result == "ok"
        assert mock_post.call_count == 2

    @patch("src.features.llm.client.httpx.post")
    def test_project_lookup_failure_raises(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError if project lookup fails."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        client = GeminiCodeAssistClient(access_token="ya29.test")  # noqa: S106

        with pytest.raises(LlmApiError, match="project lookup"):
            client.generate_content("Test")


class TestAuthRetry:
    """Tests for 401/403 auto-refresh behaviour."""

    @patch("src.features.llm.client.httpx.post")
    def test_401_with_refresher_retries_successfully(
        self, mock_post: MagicMock
    ) -> None:
        """Should refresh token and retry on 401.

        After refresh, _project is invalidated so _get_project runs
        again (project lookup + generate).
        """
        # 1st generate call: 401
        auth_fail = MagicMock()
        auth_fail.status_code = 401

        # After refresh: project lookup succeeds
        project_ok = MagicMock()
        project_ok.status_code = 200
        project_ok.json.return_value = {"project": "new-project"}

        # 2nd generate call: success
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }

        mock_post.side_effect = [auth_fail, project_ok, success]

        refresher = MagicMock(return_value="ya29.new-token")
        client = GeminiCodeAssistClient(
            access_token="ya29.expired",  # noqa: S106
            token_refresher=refresher,
        )
        client._project = "test-project"  # noqa: SLF001

        result = client.generate_content("Test")

        assert result == "ok"
        refresher.assert_called_once()

    @patch("src.features.llm.client.httpx.post")
    def test_401_without_refresher_raises(self, mock_post: MagicMock) -> None:
        """Should raise immediately on 401 without a refresher."""
        auth_fail = MagicMock()
        auth_fail.status_code = 401
        mock_post.return_value = auth_fail

        client = _make_client()

        with pytest.raises(LlmApiError, match="401"):
            client.generate_content("Test")

    @patch("src.features.llm.client.httpx.post")
    def test_double_401_stops_retrying(self, mock_post: MagicMock) -> None:
        """Should not retry auth refresh more than once.

        After first refresh invalidates _project, _get_project also
        encounters 401 and triggers a second refresh. The generate
        loop's own auth check then sees auth_retried=True and raises.
        """
        auth_fail = MagicMock()
        auth_fail.status_code = 401
        mock_post.return_value = auth_fail

        refresher = MagicMock(return_value="ya29.still-bad")
        client = GeminiCodeAssistClient(
            access_token="ya29.expired",  # noqa: S106
            token_refresher=refresher,
        )
        client._project = "test-project"  # noqa: SLF001

        with pytest.raises(LlmApiError):
            client.generate_content("Test")

    @patch("src.features.llm.client.httpx.post")
    def test_project_401_triggers_refresh(self, mock_post: MagicMock) -> None:
        """Should refresh token on 401 during project lookup."""
        # First project call: 401
        project_401 = MagicMock()
        project_401.status_code = 401

        # Second project call (after refresh): success
        project_ok = MagicMock()
        project_ok.status_code = 200
        project_ok.json.return_value = {"project": "refreshed-project"}

        # Generate call: success
        generate_ok = MagicMock()
        generate_ok.status_code = 200
        generate_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }

        mock_post.side_effect = [project_401, project_ok, generate_ok]

        refresher = MagicMock(return_value="ya29.new-token")
        client = GeminiCodeAssistClient(
            access_token="ya29.expired",  # noqa: S106
            token_refresher=refresher,
        )

        result = client.generate_content("Test")

        assert result == "ok"
        refresher.assert_called_once()
