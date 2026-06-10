"""Unit tests for Gemini API key client."""

from unittest.mock import MagicMock, patch

import pytest

from src.features.llm.errors import LlmApiError
from src.features.llm.gemini_client import GeminiApiKeyClient


def _make_client(
    api_key: str = "test-api-key",  # noqa: S107
    model: str = "gemini-2.5-flash",
) -> GeminiApiKeyClient:
    """Create a test client."""
    return GeminiApiKeyClient(api_key=api_key, model=model)


class TestGeminiApiKeyClientGenerateContent:
    """Tests for GeminiApiKeyClient.generate_content."""

    @patch("src.features.llm.gemini_client.httpx.post")
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

    @patch("src.features.llm.gemini_client.httpx.post")
    def test_sends_api_key_header(self, mock_post: MagicMock) -> None:
        """Should send x-goog-api-key header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response

        client = _make_client(api_key="my-key-123")
        client.generate_content("Test")

        call_kwargs = mock_post.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["x-goog-api-key"] == "my-key-123"

    @patch("src.features.llm.gemini_client.httpx.post")
    def test_uses_correct_endpoint(self, mock_post: MagicMock) -> None:
        """Should call the generativelanguage endpoint with model name."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response

        client = _make_client(model="gemini-2.5-flash")
        client.generate_content("Test")

        url = mock_post.call_args[0][0]
        assert "generativelanguage.googleapis.com" in url
        assert "gemini-2.5-flash" in url

    @patch("src.features.llm.gemini_client.httpx.post")
    def test_sends_system_instruction(self, mock_post: MagicMock) -> None:
        """Should include systemInstruction when provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response

        client = _make_client()
        client.generate_content("Test", system_instruction="Be concise")

        body = mock_post.call_args[1]["json"]
        assert body["systemInstruction"]["parts"][0]["text"] == "Be concise"

    @patch("src.features.llm.gemini_client.httpx.post")
    def test_401_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError on 401 (no refresh for API key)."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        client = _make_client()

        with pytest.raises(LlmApiError, match="401"):
            client.generate_content("Test")

    @patch("src.features.llm.gemini_client.httpx.post")
    def test_network_error_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError on network failure."""
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")

        client = _make_client()

        with pytest.raises(LlmApiError, match="request failed"):
            client.generate_content("Test")

    @patch("src.features.llm.gemini_client.httpx.post")
    def test_empty_candidates_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError when response has no candidates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"candidates": []}
        mock_post.return_value = mock_response

        client = _make_client()

        with pytest.raises(LlmApiError, match="No candidates"):
            client.generate_content("Test")
