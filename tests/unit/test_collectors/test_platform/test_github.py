"""Unit tests for GitHub releases collector."""

import json
from unittest.mock import MagicMock

from src.collectors.errors import CollectorErrorClass
from src.collectors.platform.constants import PLATFORM_GITHUB
from src.collectors.platform.github import (
    GitHubReleasesCollector,
    extract_owner_repo,
)
from src.collectors.platform.metrics import PlatformMetrics
from src.collectors.platform.rate_limiter import (
    TokenBucketRateLimiter,
    reset_platform_rate_limiters,
)
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult
from tests.helpers.time import FIXED_NOW


class TestExtractOwnerRepo:
    """Tests for owner/repo extraction from GitHub URLs."""

    def test_https_url(self) -> None:
        """Test extraction from HTTPS URL."""
        result = extract_owner_repo("https://github.com/meta-llama/llama")
        assert result == ("meta-llama", "llama")

    def test_http_url(self) -> None:
        """Test extraction from HTTP URL."""
        result = extract_owner_repo("http://github.com/owner/repo")
        assert result == ("owner", "repo")

    def test_url_with_trailing_slash(self) -> None:
        """Test extraction from URL with trailing slash."""
        result = extract_owner_repo("https://github.com/owner/repo/")
        assert result == ("owner", "repo")

    def test_url_with_path(self) -> None:
        """Test extraction from URL with additional path."""
        result = extract_owner_repo("https://github.com/owner/repo/releases")
        assert result == ("owner", "repo")

    def test_invalid_url(self) -> None:
        """Test extraction from non-GitHub URL."""
        result = extract_owner_repo("https://gitlab.com/owner/repo")
        assert result is None

    def test_missing_repo(self) -> None:
        """Test extraction from URL without repo."""
        result = extract_owner_repo("https://github.com/owner")
        assert result is None


class TestGitHubReleasesCollector:
    """Tests for GitHubReleasesCollector."""

    def setup_method(self) -> None:
        """Reset metrics and rate limiters before each test."""
        PlatformMetrics.reset()
        reset_platform_rate_limiters()

    def _make_source_config(
        self,
        url: str = "https://github.com/meta-llama/llama",
    ) -> SourceConfig:
        """Create a test source config."""
        return SourceConfig(
            id="github-test",
            name="Test GitHub Source",
            url=url,
            tier=SourceTier.TIER_0,
            method=SourceMethod.GITHUB_RELEASES,
            kind=SourceKind.RELEASE,
            max_items=50,
        )

    def _make_release_json(
        self,
        release_id: int = 12345,
        tag_name: str = "v1.0.0",
        name: str = "Release v1.0.0",
        prerelease: bool = False,
    ) -> dict[str, object]:
        """Create a test release JSON object."""
        return {
            "id": release_id,
            "tag_name": tag_name,
            "name": name,
            "html_url": f"https://github.com/owner/repo/releases/tag/{tag_name}",
            "published_at": "2024-01-15T10:00:00Z",
            "prerelease": prerelease,
            "body": "Release notes here",
        }

    def test_collect_success(self) -> None:
        """Test successful collection."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        # Mock HTTP client
        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=json.dumps([self._make_release_json()]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_DONE
        assert result.error is None
        assert len(result.items) == 1

        item = result.items[0]
        assert item.title == "Release v1.0.0"
        assert item.url == "https://github.com/owner/repo/releases/tag/v1.0.0"
        assert item.source_id == "github-test"

    def test_collect_invalid_url(self) -> None:
        """Test collection with invalid GitHub URL."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config(url="https://gitlab.com/owner/repo")

        mock_http = MagicMock()
        now = FIXED_NOW

        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None
        assert result.error.error_class == CollectorErrorClass.SCHEMA

    def test_collect_auth_error_401(self) -> None:
        """Test 401 error produces remediation hint."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=401,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=b"Unauthorized",
            cache_hit=False,
            error=FetchError(
                error_class=FetchErrorClass.HTTP_4XX,
                message="Unauthorized",
                status_code=401,
            ),
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None
        assert "GITHUB_TOKEN" in result.error.message

    def test_collect_auth_error_403(self) -> None:
        """Test 403 error produces remediation hint."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=403,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=b"Forbidden",
            cache_hit=False,
            error=FetchError(
                error_class=FetchErrorClass.HTTP_4XX,
                message="Forbidden",
                status_code=403,
            ),
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None
        assert "GITHUB_TOKEN" in result.error.message

    def test_content_hash_changes_on_update(self) -> None:
        """Test content hash changes when release notes change."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()
        mock_http = MagicMock()

        # First version
        release1 = self._make_release_json()
        release1["body"] = "Original notes"

        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=json.dumps([release1]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result1 = collector.collect(source_config, mock_http, now)
        hash1 = result1.items[0].content_hash

        # Updated version
        release2 = self._make_release_json()
        release2["body"] = "Updated notes"

        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=json.dumps([release2]).encode(),
            cache_hit=False,
            error=None,
        )

        result2 = collector.collect(source_config, mock_http, now)
        hash2 = result2.items[0].content_hash

        assert hash1 != hash2

    def test_empty_response(self) -> None:
        """Test handling of empty releases list."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=b"[]",
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 0

    def test_metrics_recorded(self) -> None:
        """Test that metrics are recorded."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = GitHubReleasesCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api.github.com/repos/meta-llama/llama/releases",
            headers={},
            body_bytes=json.dumps([self._make_release_json()]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        collector.collect(source_config, mock_http, now)

        metrics = PlatformMetrics.get_instance()
        assert metrics.get_api_calls_total(PLATFORM_GITHUB) == 1
