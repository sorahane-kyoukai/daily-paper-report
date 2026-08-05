"""Contract tests for the dedicated DeepSeek V4 Flash client."""

from unittest.mock import MagicMock, patch

import pytest

from src.features.llm.deepseek_client import (
    CONTEXT_LIMIT_TOKENS,
    DeepSeekClient,
)
from src.features.llm.errors import LlmApiError


def _response(content: str = '{"ok":true}') -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
        },
    }
    return response


@patch("src.features.llm.deepseek_client.httpx.post")
def test_request_is_v4_flash_json_mode(mock_post: MagicMock) -> None:
    mock_post.return_value = _response()
    client = DeepSeekClient(api_key="secret")
    assert client.generate_content("Return json", "System") == '{"ok":true}'
    body = mock_post.call_args.kwargs["json"]
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert CONTEXT_LIMIT_TOKENS == 1_000_000
    assert client.last_usage.prompt_cache_hit_tokens == 80


@patch("src.features.llm.deepseek_client.httpx.post")
def test_retry_after_is_honored(mock_post: MagicMock) -> None:
    limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
    mock_post.side_effect = [limited, _response()]
    client = DeepSeekClient(api_key="secret")
    assert client.generate_content("json")
    assert mock_post.call_count == 2


@patch("src.features.llm.deepseek_client.httpx.post")
def test_non_retryable_error_fails(mock_post: MagicMock) -> None:
    mock_post.return_value = MagicMock(status_code=401, headers={})
    with pytest.raises(LlmApiError, match="401"):
        DeepSeekClient(api_key="secret").generate_content("json")


def test_other_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="deepseek-v4-flash"):
        DeepSeekClient(api_key="secret", model="other")
