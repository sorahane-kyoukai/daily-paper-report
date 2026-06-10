"""Unit tests for HuggingFace org collector."""

import json
from unittest.mock import MagicMock

from src.collectors.errors import CollectorErrorClass
from src.collectors.platform.constants import PLATFORM_HUGGINGFACE
from src.collectors.platform.huggingface import (
    HuggingFaceOrgCollector,
    extract_org,
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


class TestExtractOrg:
    """Tests for org extraction from HuggingFace URLs."""

    def test_https_url(self) -> None:
        """Test extraction from HTTPS URL."""
        result = extract_org("https://huggingface.co/meta-llama")
        assert result == "meta-llama"

    def test_url_with_trailing_slash(self) -> None:
        """Test extraction from URL with trailing slash."""
        result = extract_org("https://huggingface.co/meta-llama/")
        assert result == "meta-llama"

    def test_invalid_url(self) -> None:
        """Test extraction from non-HuggingFace URL."""
        result = extract_org("https://github.com/meta-llama")
        assert result is None

    def test_model_url_not_org(self) -> None:
        """Test extraction from model URL (not org) returns None."""
        # Model URLs have two path segments
        result = extract_org("https://huggingface.co/meta-llama/Llama-3")
        assert result is None


class TestHuggingFaceOrgCollector:
    """Tests for HuggingFaceOrgCollector."""

    def setup_method(self) -> None:
        """Reset metrics and rate limiters before each test."""
        PlatformMetrics.reset()
        reset_platform_rate_limiters()

    def _make_source_config(
        self,
        url: str = "https://huggingface.co/meta-llama",
    ) -> SourceConfig:
        """Create a test source config."""
        return SourceConfig(
            id="hf-test",
            name="Test HF Source",
            url=url,
            tier=SourceTier.TIER_0,
            method=SourceMethod.HF_ORG,
            kind=SourceKind.MODEL,
            max_items=50,
        )

    def _make_model_json(
        self,
        model_id: str = "meta-llama/Llama-3-8B",
        pipeline_tag: str = "text-generation",
    ) -> dict[str, object]:
        """Create a test model JSON object."""
        return {
            "id": model_id,
            "modelId": model_id,
            "author": "meta-llama",
            "lastModified": "2024-01-15T10:00:00.000Z",
            "pipeline_tag": pipeline_tag,
            "downloads": 1000000,
            "likes": 5000,
            "cardData": {"license": "llama2"},
        }

    def test_collect_success(self) -> None:
        """Test successful collection."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://huggingface.co/api/models",
            headers={},
            body_bytes=json.dumps([self._make_model_json()]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_DONE
        assert result.error is None
        assert len(result.items) == 1

        item = result.items[0]
        assert item.title == "meta-llama/Llama-3-8B"
        assert item.url == "https://huggingface.co/meta-llama/Llama-3-8B"
        assert item.source_id == "hf-test"

    def test_collect_invalid_url(self) -> None:
        """Test collection with invalid HuggingFace URL."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config(url="https://github.com/meta-llama")

        mock_http = MagicMock()
        now = FIXED_NOW

        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None
        assert result.error.error_class == CollectorErrorClass.SCHEMA

    def test_collect_auth_error(self) -> None:
        """Test 401 error produces remediation hint."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=401,
            final_url="https://huggingface.co/api/models",
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
        assert "HF_TOKEN" in result.error.message

    def test_content_hash_changes_on_update(self) -> None:
        """Test content hash changes when lastModified changes."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()
        mock_http = MagicMock()

        # First version
        model1 = self._make_model_json()
        model1["lastModified"] = "2024-01-15T10:00:00.000Z"

        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://huggingface.co/api/models",
            headers={},
            body_bytes=json.dumps([model1]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result1 = collector.collect(source_config, mock_http, now)
        hash1 = result1.items[0].content_hash

        # Updated version
        model2 = self._make_model_json()
        model2["lastModified"] = "2024-01-16T10:00:00.000Z"

        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://huggingface.co/api/models",
            headers={},
            body_bytes=json.dumps([model2]).encode(),
            cache_hit=False,
            error=None,
        )

        result2 = collector.collect(source_config, mock_http, now)
        hash2 = result2.items[0].content_hash

        assert hash1 != hash2

    def test_empty_response(self) -> None:
        """Test handling of empty models list."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://huggingface.co/api/models",
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
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://huggingface.co/api/models",
            headers={},
            body_bytes=json.dumps([self._make_model_json()]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        collector.collect(source_config, mock_http, now)

        metrics = PlatformMetrics.get_instance()
        assert metrics.get_api_calls_total(PLATFORM_HUGGINGFACE) == 1

    def test_license_extraction(self) -> None:
        """Test license is extracted from model data."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = HuggingFaceOrgCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        model = self._make_model_json()
        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://huggingface.co/api/models",
            headers={},
            body_bytes=json.dumps([model]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        item = result.items[0]
        raw = json.loads(item.raw_json)
        assert raw.get("license") == "llama2"
