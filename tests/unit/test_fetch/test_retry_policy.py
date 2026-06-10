"""Unit tests for retry policy decisions."""

import pytest

from src.features.fetch.models import FetchError, FetchErrorClass, RetryPolicy


class TestRetryPolicy:
    """Tests for RetryPolicy model."""

    def test_default_values(self) -> None:
        """Test default retry policy values."""
        policy = RetryPolicy()

        assert policy.max_retries == 3
        assert policy.base_delay_ms == 1000
        assert policy.max_delay_ms == 30000
        assert policy.exponential_base == 2.0
        assert policy.jitter_factor == 0.1

    def test_custom_values(self) -> None:
        """Test custom retry policy values."""
        policy = RetryPolicy(
            max_retries=5,
            base_delay_ms=500,
            max_delay_ms=60000,
            exponential_base=1.5,
            jitter_factor=0.2,
        )

        assert policy.max_retries == 5
        assert policy.base_delay_ms == 500
        assert policy.max_delay_ms == 60000
        assert policy.exponential_base == 1.5
        assert policy.jitter_factor == 0.2


class TestShouldRetry:
    """Tests for retry decision logic."""

    @pytest.fixture
    def policy(self) -> RetryPolicy:
        """Create a standard retry policy."""
        return RetryPolicy(max_retries=3)

    def test_retry_on_network_timeout(self, policy: RetryPolicy) -> None:
        """Test that network timeouts are retried."""
        error = FetchError(
            error_class=FetchErrorClass.NETWORK_TIMEOUT,
            message="Connection timed out",
        )

        assert policy.should_retry(error, attempt=0) is True
        assert policy.should_retry(error, attempt=1) is True
        assert policy.should_retry(error, attempt=2) is True
        assert policy.should_retry(error, attempt=3) is False  # Max reached

    def test_retry_on_connection_error(self, policy: RetryPolicy) -> None:
        """Test that connection errors are retried."""
        error = FetchError(
            error_class=FetchErrorClass.CONNECTION_ERROR,
            message="Connection refused",
        )

        assert policy.should_retry(error, attempt=0) is True
        assert policy.should_retry(error, attempt=2) is True
        assert policy.should_retry(error, attempt=3) is False

    def test_retry_on_5xx(self, policy: RetryPolicy) -> None:
        """Test that 5xx errors are retried."""
        error = FetchError(
            error_class=FetchErrorClass.HTTP_5XX,
            message="Internal Server Error",
            status_code=500,
        )

        assert policy.should_retry(error, attempt=0) is True
        assert policy.should_retry(error, attempt=1) is True

    def test_retry_on_503(self, policy: RetryPolicy) -> None:
        """Test that 503 Service Unavailable is retried."""
        error = FetchError(
            error_class=FetchErrorClass.HTTP_5XX,
            message="Service Unavailable",
            status_code=503,
        )

        assert policy.should_retry(error, attempt=0) is True

    def test_retry_on_429_rate_limited(self, policy: RetryPolicy) -> None:
        """Test that 429 rate limited errors are retried."""
        error = FetchError(
            error_class=FetchErrorClass.RATE_LIMITED,
            message="Too Many Requests",
            status_code=429,
            retry_after=60,
        )

        assert policy.should_retry(error, attempt=0) is True
        assert policy.should_retry(error, attempt=2) is True

    def test_no_retry_on_4xx(self, policy: RetryPolicy) -> None:
        """Test that 4xx errors (except 429) are not retried."""
        for status in [400, 401, 403, 404, 405, 410, 422]:
            error = FetchError(
                error_class=FetchErrorClass.HTTP_4XX,
                message=f"Client error {status}",
                status_code=status,
            )

            assert policy.should_retry(error, attempt=0) is False

    def test_no_retry_on_response_size_exceeded(self, policy: RetryPolicy) -> None:
        """Test that size exceeded errors are not retried."""
        error = FetchError(
            error_class=FetchErrorClass.RESPONSE_SIZE_EXCEEDED,
            message="Response too large",
        )

        assert policy.should_retry(error, attempt=0) is False

    def test_no_retry_on_ssl_error(self, policy: RetryPolicy) -> None:
        """Test that SSL errors are not retried."""
        error = FetchError(
            error_class=FetchErrorClass.SSL_ERROR,
            message="Certificate verification failed",
        )

        assert policy.should_retry(error, attempt=0) is False

    def test_no_retry_when_max_reached(self, policy: RetryPolicy) -> None:
        """Test that retries stop when max is reached."""
        error = FetchError(
            error_class=FetchErrorClass.HTTP_5XX,
            message="Server Error",
            status_code=500,
        )

        # Max retries is 3, so attempt 3 (4th try) should not retry
        assert policy.should_retry(error, attempt=3) is False
        assert policy.should_retry(error, attempt=4) is False

    def test_zero_max_retries(self) -> None:
        """Test policy with zero max retries."""
        policy = RetryPolicy(max_retries=0)
        error = FetchError(
            error_class=FetchErrorClass.HTTP_5XX,
            message="Server Error",
            status_code=500,
        )

        assert policy.should_retry(error, attempt=0) is False


class TestGetDelayMs:
    """Tests for retry delay calculation."""

    def test_exponential_backoff(self) -> None:
        """Test that delays increase exponentially."""
        policy = RetryPolicy(
            base_delay_ms=1000,
            exponential_base=2.0,
            jitter_factor=0.0,  # No jitter for deterministic test
        )

        assert policy.get_delay_ms(0) == 1000  # 1000 * 2^0 = 1000
        assert policy.get_delay_ms(1) == 2000  # 1000 * 2^1 = 2000
        assert policy.get_delay_ms(2) == 4000  # 1000 * 2^2 = 4000
        assert policy.get_delay_ms(3) == 8000  # 1000 * 2^3 = 8000

    def test_max_delay_cap(self) -> None:
        """Test that delay is capped at max_delay_ms."""
        policy = RetryPolicy(
            base_delay_ms=1000,
            max_delay_ms=5000,
            exponential_base=2.0,
            jitter_factor=0.0,
        )

        assert policy.get_delay_ms(0) == 1000
        assert policy.get_delay_ms(1) == 2000
        assert policy.get_delay_ms(2) == 4000
        assert policy.get_delay_ms(3) == 5000  # Capped at max
        assert policy.get_delay_ms(10) == 5000  # Still capped

    def test_jitter_adds_variation(self) -> None:
        """Test that jitter adds variation to delays."""
        policy = RetryPolicy(
            base_delay_ms=1000,
            jitter_factor=0.1,
        )

        # With jitter, delays should vary
        delays = [policy.get_delay_ms(0) for _ in range(10)]

        # All delays should be >= base and < base * (1 + jitter)
        for delay in delays:
            assert 1000 <= delay <= 1100

    def test_custom_exponential_base(self) -> None:
        """Test custom exponential base."""
        policy = RetryPolicy(
            base_delay_ms=1000,
            exponential_base=3.0,
            jitter_factor=0.0,
        )

        assert policy.get_delay_ms(0) == 1000  # 1000 * 3^0 = 1000
        assert policy.get_delay_ms(1) == 3000  # 1000 * 3^1 = 3000
        assert policy.get_delay_ms(2) == 9000  # 1000 * 3^2 = 9000


class TestFetchErrorClass:
    """Tests for FetchErrorClass enum."""

    def test_all_error_classes_exist(self) -> None:
        """Test that all expected error classes exist."""
        expected = [
            "NETWORK_TIMEOUT",
            "CONNECTION_ERROR",
            "RESPONSE_SIZE_EXCEEDED",
            "HTTP_4XX",
            "HTTP_5XX",
            "RATE_LIMITED",
            "SSL_ERROR",
            "UNKNOWN",
        ]

        for name in expected:
            assert hasattr(FetchErrorClass, name)
            assert FetchErrorClass[name].value == name


class TestFetchError:
    """Tests for FetchError model."""

    def test_basic_error(self) -> None:
        """Test creating a basic error."""
        error = FetchError(
            error_class=FetchErrorClass.HTTP_5XX,
            message="Internal Server Error",
            status_code=500,
        )

        assert error.error_class == FetchErrorClass.HTTP_5XX
        assert error.message == "Internal Server Error"
        assert error.status_code == 500
        assert error.retry_after is None

    def test_rate_limited_with_retry_after(self) -> None:
        """Test rate limited error with retry_after."""
        error = FetchError(
            error_class=FetchErrorClass.RATE_LIMITED,
            message="Too Many Requests",
            status_code=429,
            retry_after=120,
        )

        assert error.error_class == FetchErrorClass.RATE_LIMITED
        assert error.retry_after == 120

    def test_error_immutable(self) -> None:
        """Test that error is immutable (frozen)."""
        from pydantic import ValidationError

        error = FetchError(
            error_class=FetchErrorClass.HTTP_4XX,
            message="Not Found",
            status_code=404,
        )

        with pytest.raises(ValidationError):
            error.status_code = 500  # type: ignore[misc]
