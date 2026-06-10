"""Integration tests for platform collectors."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from src.collectors.platform.constants import (
    PLATFORM_GITHUB,
    PLATFORM_HUGGINGFACE,
    PLATFORM_OPENREVIEW,
)
from src.collectors.platform.github import GitHubReleasesCollector
from src.collectors.platform.huggingface import HuggingFaceOrgCollector
from src.collectors.platform.metrics import PlatformMetrics
from src.collectors.platform.openreview import OpenReviewVenueCollector
from src.collectors.platform.rate_limiter import (
    TokenBucketRateLimiter,
    reset_platform_rate_limiters,
)
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.models import FetchResult
from tests.helpers.time import FIXED_NOW


@pytest.fixture
def reset_state() -> None:
    """Reset global state before each test."""
    PlatformMetrics.reset()
    reset_platform_rate_limiters()


class TestRateLimitingIntegration:
    """Integration tests for rate limiting behavior."""

    def test_rate_limiter_enforces_qps(self, reset_state: None) -> None:
        """Test rate limiter enforces max QPS."""
        # Low QPS to make timing observable
        limiter = TokenBucketRateLimiter(max_qps=5.0, bucket_capacity=1.0)

        # Drain the bucket
        limiter.acquire(1)

        # Time 5 more acquires
        start = time.monotonic()
        for _ in range(5):
            limiter.acquire(1)
        elapsed = time.monotonic() - start

        # At 5 QPS with bucket drained, 5 tokens takes ~1 second
        assert elapsed >= 0.9
        assert elapsed < 1.5

    def test_concurrent_rate_limiting(self, reset_state: None) -> None:
        """Test rate limiting works correctly under concurrent access."""
        limiter = TokenBucketRateLimiter(max_qps=20.0, bucket_capacity=5.0)

        def acquire_sequence(n: int) -> list[float]:
            times = []
            for _ in range(n):
                limiter.acquire(1)
                times.append(time.monotonic())
            return times

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(acquire_sequence, 5) for _ in range(4)]
            all_times = []
            for f in futures:
                all_times.extend(f.result())

        # 20 total acquires at 20 QPS should take ~1 second
        # (5 initial tokens used immediately, then 15 more over ~0.75s)
        total_time = max(all_times) - min(all_times)
        assert total_time >= 0.5


class TestCollectorIntegration:
    """Integration tests for platform collectors working together."""

    def _make_mock_http(
        self,
        responses: dict[str, bytes],
    ) -> MagicMock:
        """Create a mock HTTP client with multiple responses."""
        mock = MagicMock()

        def fetch_side_effect(
            source_id: str,
            url: str,
            extra_headers: dict[str, str] | None = None,
        ) -> FetchResult:
            for pattern, body in responses.items():
                if pattern in url:
                    return FetchResult(
                        status_code=200,
                        final_url=url,
                        headers={},
                        body_bytes=body,
                        cache_hit=False,
                        error=None,
                    )
            return FetchResult(
                status_code=404,
                final_url=url,
                headers={},
                body_bytes=b"Not found",
                cache_hit=False,
                error=None,
            )

        mock.fetch.side_effect = fetch_side_effect
        return mock

    def test_multiple_platforms_parallel(self, reset_state: None) -> None:
        """Test multiple platform collectors can run in parallel."""
        # Setup rate limiters with high QPS for fast tests
        gh_limiter = TokenBucketRateLimiter(max_qps=100.0)
        hf_limiter = TokenBucketRateLimiter(max_qps=100.0)
        or_limiter = TokenBucketRateLimiter(max_qps=100.0)

        collectors = {
            "github": GitHubReleasesCollector(run_id="test", rate_limiter=gh_limiter),
            "huggingface": HuggingFaceOrgCollector(
                run_id="test", rate_limiter=hf_limiter
            ),
            "openreview": OpenReviewVenueCollector(
                run_id="test", rate_limiter=or_limiter
            ),
        }

        configs = {
            "github": SourceConfig(
                id="gh-test",
                name="GitHub Test",
                url="https://github.com/test/repo",
                tier=SourceTier.TIER_0,
                method=SourceMethod.GITHUB_RELEASES,
                kind=SourceKind.RELEASE,
            ),
            "huggingface": SourceConfig(
                id="hf-test",
                name="HF Test",
                url="https://huggingface.co/test-org",
                tier=SourceTier.TIER_0,
                method=SourceMethod.HF_ORG,
                kind=SourceKind.MODEL,
            ),
            "openreview": SourceConfig(
                id="or-test",
                name="OR Test",
                url="https://openreview.net/group?id=Test",
                tier=SourceTier.TIER_1,
                method=SourceMethod.OPENREVIEW_VENUE,
                kind=SourceKind.PAPER,
                query="Test/Venue/-/Submission",
            ),
        }

        # Create mock responses
        responses = {
            "api.github.com": json.dumps(
                [
                    {
                        "id": 1,
                        "tag_name": "v1.0",
                        "name": "Release 1",
                        "html_url": "https://github.com/test/repo/releases/tag/v1.0",
                        "published_at": "2024-01-15T10:00:00Z",
                    }
                ]
            ).encode(),
            "huggingface.co/api": json.dumps(
                [
                    {
                        "id": "test-org/model-1",
                        "lastModified": "2024-01-15T10:00:00.000Z",
                    }
                ]
            ).encode(),
            "api2.openreview.net": json.dumps(
                {
                    "notes": [
                        {
                            "forum": "abc123",
                            "cdate": 1705312800000,
                            "content": {"title": {"value": "Paper 1"}},
                        }
                    ]
                }
            ).encode(),
        }

        mock_http = self._make_mock_http(responses)
        now = FIXED_NOW

        results = {}

        def run_collector(platform: str) -> None:
            result = collectors[platform].collect(configs[platform], mock_http, now)
            results[platform] = result

        # Run in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_collector, p) for p in collectors]
            for f in futures:
                f.result()

        # All should succeed
        for platform, result in results.items():
            assert result.state == SourceState.SOURCE_DONE, f"{platform} failed"
            assert len(result.items) == 1, f"{platform} has wrong item count"

        # Check metrics
        metrics = PlatformMetrics.get_instance()
        assert metrics.get_api_calls_total(PLATFORM_GITHUB) == 1
        assert metrics.get_api_calls_total(PLATFORM_HUGGINGFACE) == 1
        assert metrics.get_api_calls_total(PLATFORM_OPENREVIEW) == 1


class TestDeduplicationIntegration:
    """Integration tests for deduplication behavior."""

    def test_same_items_produce_same_hash(self, reset_state: None) -> None:
        """Test identical items produce identical content hashes."""
        limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=limiter)

        config = SourceConfig(
            id="gh-test",
            name="Test",
            url="https://github.com/test/repo",
            tier=SourceTier.TIER_0,
            method=SourceMethod.GITHUB_RELEASES,
            kind=SourceKind.RELEASE,
        )

        release_data = json.dumps(
            [
                {
                    "id": 1,
                    "tag_name": "v1.0",
                    "name": "Release 1",
                    "html_url": "https://github.com/test/repo/releases/tag/v1.0",
                    "published_at": "2024-01-15T10:00:00Z",
                    "body": "Release notes",
                }
            ]
        ).encode()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/test/repo/releases",
            headers={},
            body_bytes=release_data,
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW

        # Run twice
        result1 = collector.collect(config, mock_http, now)
        result2 = collector.collect(config, mock_http, now)

        # Same content hash
        assert result1.items[0].content_hash == result2.items[0].content_hash
        # Same canonical URL
        assert result1.items[0].url == result2.items[0].url

    def test_updated_items_produce_different_hash(self, reset_state: None) -> None:
        """Test updated items produce different content hashes."""
        limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=limiter)

        config = SourceConfig(
            id="gh-test",
            name="Test",
            url="https://github.com/test/repo",
            tier=SourceTier.TIER_0,
            method=SourceMethod.GITHUB_RELEASES,
            kind=SourceKind.RELEASE,
        )

        mock_http = MagicMock()
        now = FIXED_NOW

        # First version
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/test/repo/releases",
            headers={},
            body_bytes=json.dumps(
                [
                    {
                        "id": 1,
                        "tag_name": "v1.0",
                        "name": "Release 1",
                        "html_url": "https://github.com/test/repo/releases/tag/v1.0",
                        "published_at": "2024-01-15T10:00:00Z",
                        "body": "Original notes",
                    }
                ]
            ).encode(),
            cache_hit=False,
            error=None,
        )

        result1 = collector.collect(config, mock_http, now)

        # Updated version (body changed)
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/test/repo/releases",
            headers={},
            body_bytes=json.dumps(
                [
                    {
                        "id": 1,
                        "tag_name": "v1.0",
                        "name": "Release 1",
                        "html_url": "https://github.com/test/repo/releases/tag/v1.0",
                        "published_at": "2024-01-15T10:00:00Z",
                        "body": "Updated notes with new information",
                    }
                ]
            ).encode(),
            cache_hit=False,
            error=None,
        )

        result2 = collector.collect(config, mock_http, now)

        # Different content hash (body changed)
        assert result1.items[0].content_hash != result2.items[0].content_hash
        # Same canonical URL
        assert result1.items[0].url == result2.items[0].url
