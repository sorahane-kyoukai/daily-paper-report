"""Unit tests for token-bucket rate limiter."""

import time
from concurrent.futures import ThreadPoolExecutor

from src.collectors.platform.rate_limiter import (
    TokenBucketRateLimiter,
    get_platform_rate_limiter,
    reset_platform_rate_limiters,
)


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    def test_initial_tokens(self) -> None:
        """Test that bucket starts full."""
        limiter = TokenBucketRateLimiter(max_qps=10.0)
        assert limiter.get_available_tokens() == 10.0

    def test_try_acquire_success(self) -> None:
        """Test successful non-blocking acquire."""
        limiter = TokenBucketRateLimiter(max_qps=10.0)
        assert limiter.try_acquire(1) is True
        assert limiter.get_available_tokens() < 10.0

    def test_try_acquire_failure(self) -> None:
        """Test failed non-blocking acquire when no tokens."""
        limiter = TokenBucketRateLimiter(max_qps=1.0, bucket_capacity=1.0)
        assert limiter.try_acquire(1) is True
        assert limiter.try_acquire(1) is False
        assert limiter.was_rate_limited is True

    def test_acquire_blocking(self) -> None:
        """Test blocking acquire waits for tokens."""
        limiter = TokenBucketRateLimiter(max_qps=10.0, bucket_capacity=1.0)

        # Drain the bucket
        assert limiter.try_acquire(1) is True

        # Next acquire should block and wait
        start = time.monotonic()
        assert limiter.acquire(1) is True
        elapsed = time.monotonic() - start

        # Should have waited approximately 0.1 seconds (1 token / 10 QPS)
        assert elapsed >= 0.08  # Allow some tolerance

    def test_token_refill(self) -> None:
        """Test tokens refill over time."""
        limiter = TokenBucketRateLimiter(max_qps=100.0, bucket_capacity=10.0)

        # Drain bucket
        for _ in range(10):
            limiter.try_acquire(1)

        assert limiter.get_available_tokens() < 1.0

        # Wait for refill
        time.sleep(0.05)  # 5 tokens should refill at 100 QPS

        assert limiter.get_available_tokens() >= 4.0

    def test_bucket_capacity(self) -> None:
        """Test bucket doesn't exceed capacity."""
        limiter = TokenBucketRateLimiter(max_qps=100.0, bucket_capacity=5.0)

        # Wait for potential overfill
        time.sleep(0.1)

        assert limiter.get_available_tokens() <= 5.0

    def test_rate_limited_count(self) -> None:
        """Test rate limited event counting."""
        limiter = TokenBucketRateLimiter(max_qps=1.0, bucket_capacity=1.0)

        assert limiter.rate_limited_count == 0

        limiter.try_acquire(1)
        assert limiter.rate_limited_count == 0

        limiter.try_acquire(1)  # Should fail
        assert limiter.rate_limited_count == 1

        limiter.try_acquire(1)  # Should fail again
        assert limiter.rate_limited_count == 2

    def test_reset_stats(self) -> None:
        """Test resetting rate limit statistics."""
        limiter = TokenBucketRateLimiter(max_qps=1.0, bucket_capacity=1.0)

        limiter.try_acquire(1)
        limiter.try_acquire(1)  # Will fail
        assert limiter.rate_limited_count == 1

        limiter.reset_stats()
        assert limiter.rate_limited_count == 0

    def test_thread_safety(self) -> None:
        """Test rate limiter is thread-safe."""
        # Use low QPS so tokens don't refill significantly during test
        limiter = TokenBucketRateLimiter(max_qps=10.0, bucket_capacity=100.0)

        def acquire_many(n: int) -> int:
            success = 0
            for _ in range(n):
                if limiter.try_acquire(1):
                    success += 1
            return success

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(acquire_many, 20) for _ in range(10)]
            total_success = sum(f.result() for f in futures)

        # At least 100 tokens should be acquired (initial bucket)
        # May be slightly more due to refill during execution (~10/sec)
        assert 100 <= total_success <= 110


class TestPlatformRateLimiters:
    """Tests for platform-specific rate limiters."""

    def setup_method(self) -> None:
        """Reset rate limiters before each test."""
        reset_platform_rate_limiters()

    def test_get_platform_rate_limiter_creates_new(self) -> None:
        """Test creating a new platform limiter."""
        limiter = get_platform_rate_limiter("github", 10.0)
        assert isinstance(limiter, TokenBucketRateLimiter)
        assert limiter.max_qps == 10.0

    def test_get_platform_rate_limiter_returns_same(self) -> None:
        """Test same platform returns same limiter."""
        limiter1 = get_platform_rate_limiter("github", 10.0)
        limiter2 = get_platform_rate_limiter("github", 20.0)  # Different QPS ignored
        assert limiter1 is limiter2

    def test_different_platforms_have_different_limiters(self) -> None:
        """Test different platforms get different limiters."""
        limiter_gh = get_platform_rate_limiter("github", 10.0)
        limiter_hf = get_platform_rate_limiter("huggingface", 10.0)
        assert limiter_gh is not limiter_hf
