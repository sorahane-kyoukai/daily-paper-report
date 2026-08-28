"""Contract tests for the OpenAI-compatible chat client (OpenRouter)."""

from unittest.mock import MagicMock, patch

import pytest

from src.features.llm.errors import LlmApiError
from src.features.llm.openai_client import CONTEXT_LIMIT_TOKENS, OpenAICompatibleClient


def _response(content: str = '{"ok":true}') -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "prompt_tokens_details": {"cached_tokens": 80},
        },
    }
    return response


@patch("src.features.llm.openai_client.httpx.post")
def test_request_uses_json_mode_and_excludes_reasoning(mock_post: MagicMock) -> None:
    mock_post.return_value = _response()
    client = OpenAICompatibleClient(api_key="secret")
    assert client.generate_content("Return json", "System") == '{"ok":true}'
    body = mock_post.call_args.kwargs["json"]
    assert body["model"] == "z-ai/glm-5.3-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning"] == {"exclude": True}
    assert body["max_tokens"] == 8192
    assert mock_post.call_args.args[0] == (
        "https://openrouter.ai/api/v1/chat/completions"
    )
    assert CONTEXT_LIMIT_TOKENS == 1_000_000
    assert client.last_usage.prompt_cache_hit_tokens == 80
    assert client.last_usage.prompt_cache_miss_tokens == 20


@patch("src.features.llm.openai_client.httpx.post")
def test_non_openrouter_base_url_skips_reasoning_field(mock_post: MagicMock) -> None:
    mock_post.return_value = _response()
    client = OpenAICompatibleClient(
        api_key="secret", base_url="https://api.deepseek.com"
    )
    client.generate_content("Return json")
    body = mock_post.call_args.kwargs["json"]
    assert "reasoning" not in body
    assert mock_post.call_args.args[0] == "https://api.deepseek.com/chat/completions"


@patch("src.features.llm.openai_client.httpx.post")
def test_retry_after_is_honored(mock_post: MagicMock) -> None:
    limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
    mock_post.side_effect = [limited, _response()]
    client = OpenAICompatibleClient(api_key="secret")
    assert client.generate_content("json")
    assert mock_post.call_count == 2


@patch("src.features.llm.openai_client.httpx.post")
def test_non_retryable_error_fails(mock_post: MagicMock) -> None:
    mock_post.return_value = MagicMock(status_code=401, headers={})
    with pytest.raises(LlmApiError, match="401"):
        OpenAICompatibleClient(api_key="secret").generate_content("json")


@patch("src.features.llm.openai_client.httpx.post")
def test_provider_error_object_is_surfaced(mock_post: MagicMock) -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"error": {"message": "rate limited upstream"}}
    mock_post.return_value = response
    with pytest.raises(LlmApiError, match="rate limited upstream"):
        OpenAICompatibleClient(api_key="secret").generate_content("json")


@patch("src.features.llm.openai_client.httpx.post")
def test_empty_content_fails(mock_post: MagicMock) -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": None}}]}
    mock_post.return_value = response
    with pytest.raises(LlmApiError, match="empty content"):
        OpenAICompatibleClient(api_key="secret").generate_content("json")


def test_empty_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="model must be"):
        OpenAICompatibleClient(api_key="secret", model="")
