"""Token-bucket rate limiter for platform API calls."""

import threading
import time
from dataclasses import dataclass, field
from typing import Protocol


class RateLimiterProtocol(Protocol):
    """Protocol for rate limiters.

    Allows dependency injection of rate limiter for testing.
    """

    def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens, blocking until available.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired successfully.
        """
        ...

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without blocking.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired, False otherwise.
        """
        ...

    @property
    def was_rate_limited(self) -> bool:
        """Check if any request was rate limited since last reset."""
        ...


@dataclass
class TokenBucketRateLimiter:
    """Token bucket rate limiter for API QPS control.

    Implements a token bucket algorithm with configurable max QPS.
    Tokens are replenished continuously based on the configured rate.

    Thread-safe implementation for use with concurrent collectors.

    Attributes:
        max_qps: Maximum queries per second.
        bucket_capacity: Maximum tokens in the bucket (burst capacity).
    """

    max_qps: float
    bucket_capacity: float = 0.0  # Will be set to max_qps if 0

    _tokens: float = field(init=False, default=0.0)
    _last_refill: float = field(init=False, default=0.0)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _rate_limited_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        """Initialize the rate limiter state."""
        if self.bucket_capacity <= 0:
            self.bucket_capacity = self.max_qps
        self._tokens = self.bucket_capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time.

        Must be called while holding the lock.
        """
        now = time.monotonic()
        elapsed = now - self._last_refill
        tokens_to_add = elapsed * self.max_qps
        self._tokens = min(self.bucket_capacity, self._tokens + tokens_to_add)
        self._last_refill = now

    def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens, blocking until available.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired successfully.
        """
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                # Calculate wait time
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self.max_qps
                self._rate_limited_count += 1

            # Release lock before sleeping
            time.sleep(wait_time)

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without blocking.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired, False otherwise.
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            self._rate_limited_count += 1
            return False

    @property
    def was_rate_limited(self) -> bool:
        """Check if any request was rate limited since creation."""
        with self._lock:
            return self._rate_limited_count > 0

    @property
    def rate_limited_count(self) -> int:
        """Get the number of rate-limited events."""
        with self._lock:
            return self._rate_limited_count

    def reset_stats(self) -> None:
        """Reset rate limiting statistics."""
        with self._lock:
            self._rate_limited_count = 0

    def get_available_tokens(self) -> float:
        """Get the current number of available tokens.

        Returns:
            Current token count.
        """
        with self._lock:
            self._refill()
            return self._tokens


# Shared rate limiters per platform (singleton pattern)
_platform_limiters: dict[str, TokenBucketRateLimiter] = {}
_limiter_lock = threading.Lock()


def get_platform_rate_limiter(platform: str, max_qps: float) -> TokenBucketRateLimiter:
    """Get or create a rate limiter for a platform.

    Args:
        platform: Platform identifier (e.g., 'github', 'huggingface').
        max_qps: Maximum queries per second for the platform.

    Returns:
        TokenBucketRateLimiter instance for the platform.
    """
    with _limiter_lock:
        if platform not in _platform_limiters:
            _platform_limiters[platform] = TokenBucketRateLimiter(max_qps=max_qps)
        return _platform_limiters[platform]


def reset_platform_rate_limiters() -> None:
    """Reset all platform rate limiters (for testing)."""
    global _platform_limiters  # noqa: PLW0603
    with _limiter_lock:
        _platform_limiters = {}
