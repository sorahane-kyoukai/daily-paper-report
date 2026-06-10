"""Unit tests for response size enforcement."""

import pytest

from src.features.fetch.config import FetchConfig
from src.features.fetch.constants import DEFAULT_MAX_RESPONSE_SIZE_BYTES
from src.features.fetch.models import (
    FetchError,
    FetchErrorClass,
    FetchResult,
    RetryPolicy,
)


class TestMaxResponseSizeConfig:
    """Tests for max response size configuration."""

    def test_default_max_size(self) -> None:
        """Test default max response size is 10 MB."""
        config = FetchConfig()

        assert config.max_response_size_bytes == 10 * 1024 * 1024
        assert config.max_response_size_bytes == DEFAULT_MAX_RESPONSE_SIZE_BYTES

    def test_custom_max_size(self) -> None:
        """Test custom max response size."""
        config = FetchConfig(max_response_size_bytes=5 * 1024 * 1024)

        assert config.max_response_size_bytes == 5 * 1024 * 1024

    def test_min_max_size_validation(self) -> None:
        """Test that max size has minimum of 1KB."""
        config = FetchConfig(max_response_size_bytes=1024)

        assert config.max_response_size_bytes == 1024

        with pytest.raises(ValueError):
            FetchConfig(max_response_size_bytes=100)  # Too small

    def test_max_max_size_validation(self) -> None:
        """Test that max size has maximum of 100 MB."""
        config = FetchConfig(max_response_size_bytes=100 * 1024 * 1024)

        assert config.max_response_size_bytes == 100 * 1024 * 1024

        with pytest.raises(ValueError):
            FetchConfig(max_response_size_bytes=200 * 1024 * 1024)  # Too large


class TestResponseSizeExceededError:
    """Tests for response size exceeded error handling."""

    def test_error_class_exists(self) -> None:
        """Test that RESPONSE_SIZE_EXCEEDED error class exists."""
        assert FetchErrorClass.RESPONSE_SIZE_EXCEEDED.value == "RESPONSE_SIZE_EXCEEDED"

    def test_size_exceeded_error_not_retryable(self) -> None:
        """Test that size exceeded errors are not retried."""
        policy = RetryPolicy(max_retries=3)
        error = FetchError(
            error_class=FetchErrorClass.RESPONSE_SIZE_EXCEEDED,
            message="Response size 15MB exceeds limit 10MB",
            status_code=200,
        )

        assert policy.should_retry(error, attempt=0) is False
        assert policy.should_retry(error, attempt=1) is False

    def test_size_exceeded_error_construction(self) -> None:
        """Test constructing a size exceeded error."""
        error = FetchError(
            error_class=FetchErrorClass.RESPONSE_SIZE_EXCEEDED,
            message="Response size 15728640 exceeds limit 10485760",
            status_code=200,
        )

        assert error.error_class == FetchErrorClass.RESPONSE_SIZE_EXCEEDED
        assert "15728640" in error.message
        assert error.status_code == 200

    def test_fetch_result_with_size_error(self) -> None:
        """Test FetchResult with size exceeded error."""
        error = FetchError(
            error_class=FetchErrorClass.RESPONSE_SIZE_EXCEEDED,
            message="Response too large",
        )
        result = FetchResult(
            status_code=200,
            final_url="https://example.com/large-file",
            headers={"Content-Length": "15728640"},
            body_bytes=b"",
            cache_hit=False,
            error=error,
        )

        assert result.is_success is False
        assert result.error is not None
        assert result.error.error_class == FetchErrorClass.RESPONSE_SIZE_EXCEEDED
        assert result.body_size == 0


class TestFetchResultBodySize:
    """Tests for FetchResult body size property."""

    def test_body_size_empty(self) -> None:
        """Test body_size for empty response."""
        result = FetchResult(
            status_code=204,
            final_url="https://example.com/resource",
            body_bytes=b"",
        )

        assert result.body_size == 0

    def test_body_size_small(self) -> None:
        """Test body_size for small response."""
        result = FetchResult(
            status_code=200,
            final_url="https://example.com/resource",
            body_bytes=b'{"key": "value"}',
        )

        assert result.body_size == 16

    def test_body_size_large(self) -> None:
        """Test body_size for larger response."""
        body = b"x" * 1_000_000  # 1 MB
        result = FetchResult(
            status_code=200,
            final_url="https://example.com/resource",
            body_bytes=body,
        )

        assert result.body_size == 1_000_000

    def test_body_size_at_limit(self) -> None:
        """Test body_size at exactly the limit."""
        body = b"x" * (10 * 1024 * 1024)  # Exactly 10 MB
        result = FetchResult(
            status_code=200,
            final_url="https://example.com/resource",
            body_bytes=body,
        )

        assert result.body_size == 10 * 1024 * 1024


class TestFetchResultSuccess:
    """Tests for FetchResult is_success property."""

    def test_success_on_200(self) -> None:
        """Test is_success for 200 OK."""
        result = FetchResult(
            status_code=200,
            final_url="https://example.com/resource",
            body_bytes=b"content",
        )

        assert result.is_success is True

    def test_success_on_201(self) -> None:
        """Test is_success for 201 Created."""
        result = FetchResult(
            status_code=201,
            final_url="https://example.com/resource",
            body_bytes=b"content",
        )

        assert result.is_success is True

    def test_not_success_on_error(self) -> None:
        """Test is_success is False when error present."""
        result = FetchResult(
            status_code=200,
            final_url="https://example.com/resource",
            body_bytes=b"",
            error=FetchError(
                error_class=FetchErrorClass.RESPONSE_SIZE_EXCEEDED,
                message="Too large",
            ),
        )

        assert result.is_success is False

    def test_not_success_on_4xx(self) -> None:
        """Test is_success is False for 4xx status."""
        result = FetchResult(
            status_code=404,
            final_url="https://example.com/resource",
            body_bytes=b"Not Found",
            error=FetchError(
                error_class=FetchErrorClass.HTTP_4XX,
                message="Not Found",
                status_code=404,
            ),
        )

        assert result.is_success is False

    def test_not_success_on_5xx(self) -> None:
        """Test is_success is False for 5xx status."""
        result = FetchResult(
            status_code=500,
            final_url="https://example.com/resource",
            body_bytes=b"",
            error=FetchError(
                error_class=FetchErrorClass.HTTP_5XX,
                message="Server Error",
                status_code=500,
            ),
        )

        assert result.is_success is False
