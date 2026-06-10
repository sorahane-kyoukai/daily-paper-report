"""Unit tests for OpenAI-compatible LLM client."""

from unittest.mock import MagicMock, patch

import pytest

from src.features.llm.errors import LlmApiError
from src.features.llm.openai_compatible_client import OpenAiCompatibleClient


def _make_client(
    api_key: str = "test-api-key",  # noqa: S107
    model: str = "test-model",
    base_url: str = "https://example.test/v1",
) -> OpenAiCompatibleClient:
    """Create a test client."""
    return OpenAiCompatibleClient(api_key=api_key, model=model, base_url=base_url)


class TestOpenAiCompatibleClientGenerateContent:
    """Tests for OpenAiCompatibleClient.generate_content."""

    @patch("src.features.llm.openai_compatible_client.httpx.post")
    def test_success_returns_message_content(self, mock_post: MagicMock) -> None:
        """Should return text from choices[0].message.content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}]
        }
        mock_post.return_value = mock_response

        client = _make_client()
        result = client.generate_content("Say hello")

        assert result == "Hello world"

    @patch("src.features.llm.openai_compatible_client.httpx.post")
    def test_sends_chat_completion_request(self, mock_post: MagicMock) -> None:
        """Should call /chat/completions with bearer auth and messages."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_response

        client = _make_client(api_key="my-key-123", model="test-model")
        client.generate_content("Test", system_instruction="Be concise")

        assert mock_post.call_args[0][0] == "https://example.test/v1/chat/completions"
        headers = mock_post.call_args[1]["headers"]
        body = mock_post.call_args[1]["json"]
        assert headers["Authorization"] == "Bearer my-key-123"
        assert body["model"] == "test-model"
        assert body["messages"] == [
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Test"},
        ]

    @patch("src.features.llm.openai_compatible_client.httpx.post")
    def test_sends_reasoning_and_thinking_options(self, mock_post: MagicMock) -> None:
        """Should include provider-specific reasoning options when configured."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_response

        client = OpenAiCompatibleClient(
            api_key="test-key",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            reasoning_effort="high",
            thinking_type="enabled",
            max_tokens=1024,
        )
        client.generate_content("Test")

        body = mock_post.call_args[1]["json"]
        assert body["reasoning_effort"] == "high"
        assert body["thinking"] == {"type": "enabled"}
        assert body["max_tokens"] == 1024

    @patch("src.features.llm.openai_compatible_client.httpx.post")
    def test_disabled_thinking_option_is_omitted(self, mock_post: MagicMock) -> None:
        """Disabled thinking means omit provider-specific thinking payload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_response

        client = OpenAiCompatibleClient(
            api_key="test-key",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            thinking_type="disabled",
        )
        client.generate_content("Test")

        body = mock_post.call_args[1]["json"]
        assert "thinking" not in body

    @patch("src.features.llm.openai_compatible_client.httpx.post")
    def test_401_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError on non-retryable auth errors."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        client = _make_client()

        with pytest.raises(LlmApiError, match="401"):
            client.generate_content("Test")

    @patch("src.features.llm.openai_compatible_client.httpx.post")
    def test_no_choices_raises_api_error(self, mock_post: MagicMock) -> None:
        """Should raise LlmApiError when response has no choices."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        mock_post.return_value = mock_response

        client = _make_client()

        with pytest.raises(LlmApiError, match="No choices"):
            client.generate_content("Test")
