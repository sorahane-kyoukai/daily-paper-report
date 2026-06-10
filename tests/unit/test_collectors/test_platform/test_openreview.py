"""Unit tests for OpenReview venue collector."""

import json
from unittest.mock import MagicMock

from src.collectors.errors import CollectorErrorClass
from src.collectors.platform.constants import PLATFORM_OPENREVIEW
from src.collectors.platform.metrics import PlatformMetrics
from src.collectors.platform.openreview import (
    OpenReviewVenueCollector,
    extract_venue_id,
)
from src.collectors.platform.rate_limiter import (
    TokenBucketRateLimiter,
    reset_platform_rate_limiters,
)
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.models import FetchError, FetchErrorClass, FetchResult
from tests.helpers.time import FIXED_NOW


class TestExtractVenueId:
    """Tests for venue ID extraction from OpenReview URLs."""

    def test_url_extraction(self) -> None:
        """Test extraction from URL."""
        result = extract_venue_id(
            "https://openreview.net/group?id=ICLR.cc/2025/Conference"
        )
        assert result == "ICLR.cc/2025/Conference"

    def test_query_field_preferred(self) -> None:
        """Test query field is preferred over URL."""
        result = extract_venue_id(
            "https://openreview.net/group?id=old-venue",
            query="ICLR.cc/2025/Conference/-/Blind_Submission",
        )
        assert result == "ICLR.cc/2025/Conference/-/Blind_Submission"

    def test_invalid_url(self) -> None:
        """Test extraction from non-OpenReview URL."""
        result = extract_venue_id("https://github.com/openreview")
        assert result is None


class TestOpenReviewVenueCollector:
    """Tests for OpenReviewVenueCollector."""

    def setup_method(self) -> None:
        """Reset metrics and rate limiters before each test."""
        PlatformMetrics.reset()
        reset_platform_rate_limiters()

    def _make_source_config(
        self,
        url: str = "https://openreview.net/group?id=ICLR.cc/2025/Conference",
        query: str | None = "ICLR.cc/2025/Conference/-/Blind_Submission",
    ) -> SourceConfig:
        """Create a test source config."""
        return SourceConfig(
            id="openreview-test",
            name="Test OpenReview Source",
            url=url,
            tier=SourceTier.TIER_1,
            method=SourceMethod.OPENREVIEW_VENUE,
            kind=SourceKind.PAPER,
            max_items=50,
            query=query,
        )

    def _make_note_json(
        self,
        forum_id: str = "abc123",
        title: str = "A Great Paper on Machine Learning",
    ) -> dict[str, object]:
        """Create a test note JSON object."""
        return {
            "id": forum_id,
            "forum": forum_id,
            "cdate": 1705312800000,  # 2024-01-15 10:00:00 UTC in ms
            "mdate": 1705312800000,
            "content": {
                "title": {"value": title},
                "authors": {"value": ["Author One", "Author Two"]},
                "pdf": {"value": "/pdf/abc123.pdf"},
            },
        }

    def test_collect_success(self) -> None:
        """Test successful collection."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": [self._make_note_json()]}).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_DONE
        assert result.error is None
        assert len(result.items) == 1

        item = result.items[0]
        assert item.title == "A Great Paper on Machine Learning"
        assert item.url == "https://openreview.net/forum?id=abc123"
        assert item.source_id == "openreview-test"

    def test_collect_invalid_url_no_query(self) -> None:
        """Test collection with invalid URL and no query."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config(
            url="https://github.com/openreview", query=None
        )

        mock_http = MagicMock()
        now = FIXED_NOW

        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_FAILED
        assert result.error is not None
        assert result.error.error_class == CollectorErrorClass.SCHEMA

    def test_collect_auth_error(self) -> None:
        """Test 401 error produces remediation hint."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=401,
            final_url="https://api2.openreview.net/notes",
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
        assert "OPENREVIEW_TOKEN" in result.error.message

    def test_content_hash_changes_on_update(self) -> None:
        """Test content hash changes when mdate changes."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()
        mock_http = MagicMock()

        # First version
        note1 = self._make_note_json()
        note1["mdate"] = 1705312800000

        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": [note1]}).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result1 = collector.collect(source_config, mock_http, now)
        hash1 = result1.items[0].content_hash

        # Updated version (mdate changed)
        note2 = self._make_note_json()
        note2["mdate"] = 1705399200000  # 24 hours later

        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": [note2]}).encode(),
            cache_hit=False,
            error=None,
        )

        result2 = collector.collect(source_config, mock_http, now)
        hash2 = result2.items[0].content_hash

        assert hash1 != hash2

    def test_empty_response(self) -> None:
        """Test handling of empty notes list."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": []}).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 0

    def test_pdf_url_extraction(self) -> None:
        """Test PDF URL is extracted correctly."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        note = self._make_note_json()
        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": [note]}).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        item = result.items[0]
        raw = json.loads(item.raw_json)
        assert raw.get("pdf_url") == "https://openreview.net/pdf/abc123.pdf"

    def test_metrics_recorded(self) -> None:
        """Test that metrics are recorded."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": [self._make_note_json()]}).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        collector.collect(source_config, mock_http, now)

        metrics = PlatformMetrics.get_instance()
        assert metrics.get_api_calls_total(PLATFORM_OPENREVIEW) == 1

    def test_timestamp_parsing_milliseconds(self) -> None:
        """Test timestamp parsing from milliseconds."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        note = self._make_note_json()
        # 2024-01-15 10:00:00 UTC in milliseconds
        note["cdate"] = 1705312800000

        mock_http = MagicMock()
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps({"notes": [note]}).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        item = result.items[0]
        assert item.published_at is not None
        assert item.published_at.year == 2024
        assert item.published_at.month == 1
        assert item.published_at.day == 15

    def test_response_array_format(self) -> None:
        """Test parsing response as direct array (not wrapped in notes key)."""
        rate_limiter = TokenBucketRateLimiter(max_qps=100.0)
        collector = OpenReviewVenueCollector(run_id="test", rate_limiter=rate_limiter)

        source_config = self._make_source_config()

        mock_http = MagicMock()
        # Some endpoints return array directly
        mock_http.fetch.return_value = FetchResult(
            status_code=200,
            final_url="https://api2.openreview.net/notes",
            headers={},
            body_bytes=json.dumps([self._make_note_json()]).encode(),
            cache_hit=False,
            error=None,
        )

        now = FIXED_NOW
        result = collector.collect(source_config, mock_http, now)

        assert result.state == SourceState.SOURCE_DONE
        assert len(result.items) == 1
