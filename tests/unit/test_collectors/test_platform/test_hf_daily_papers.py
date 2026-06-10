"""Unit tests for HuggingFace Daily Papers collector."""

import json
from unittest.mock import MagicMock

from src.collectors.arxiv.utils import extract_arxiv_id as extract_arxiv_id_from_url
from src.collectors.platform.hf_daily_papers import HuggingFaceDailyPapersCollector
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.models import FetchResult
from tests.helpers.time import FIXED_NOW


def _make_source_config() -> SourceConfig:
    """Create a test SourceConfig."""
    return SourceConfig(
        id="hf-daily-papers",
        name="HuggingFace Daily Papers",
        url="https://huggingface.co/api/daily_papers",
        tier=SourceTier.TIER_0,
        method=SourceMethod.HF_DAILY_PAPERS,
        kind=SourceKind.PAPER,
        max_items=10,
    )


def _make_fetch_result(
    status_code: int = 200,
    body: str = "[]",
) -> FetchResult:
    """Create a test FetchResult."""
    return FetchResult(
        status_code=status_code,
        final_url="https://huggingface.co/api/daily_papers",
        body_bytes=body.encode("utf-8"),
    )


class TestExtractArxivIdFromUrl:
    """Tests for extract_arxiv_id_from_url function."""

    def test_extract_from_arxiv_abs_url(self) -> None:
        """Extract arXiv ID from abs URL."""
        arxiv_id = extract_arxiv_id_from_url("https://arxiv.org/abs/2301.12345")
        assert arxiv_id == "2301.12345"

    def test_extract_from_arxiv_pdf_url(self) -> None:
        """Extract arXiv ID from PDF URL."""
        arxiv_id = extract_arxiv_id_from_url("https://arxiv.org/pdf/2301.12345.pdf")
        assert arxiv_id == "2301.12345"

    def test_returns_none_for_non_arxiv(self) -> None:
        """Return None for non-arXiv URL."""
        arxiv_id = extract_arxiv_id_from_url("https://example.com/paper")
        assert arxiv_id is None


class TestHuggingFaceDailyPapersCollector:
    """Tests for HuggingFaceDailyPapersCollector class."""

    def test_collect_success_list_format(self) -> None:
        """Successful collection with list response format."""
        api_response = json.dumps(
            [
                {
                    "paper": {
                        "id": "2301.00001",
                        "title": "Test Paper 1",
                        "authors": [{"name": "Author A"}],
                        "summary": "This is the abstract.",
                    },
                    "upvotes": 42,
                    "publishedAt": "2023-01-01T00:00:00Z",
                },
                {
                    "paper": {
                        "id": "2301.00002",
                        "title": "Test Paper 2",
                        "summary": "Another abstract.",
                    },
                    "upvotes": 10,
                    "publishedAt": "2023-01-01T01:00:00Z",
                },
            ]
        )

        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(body=api_response)
        rate_limiter = MagicMock()

        collector = HuggingFaceDailyPapersCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert result.success
        assert len(result.items) == 2
        assert result.items[0].title == "Test Paper 1"
        assert result.items[1].title == "Test Paper 2"

    def test_collect_api_error(self) -> None:
        """API error returns failed result."""
        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(
            status_code=500,
            body="Internal Server Error",
        )
        rate_limiter = MagicMock()

        collector = HuggingFaceDailyPapersCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert not result.success
        assert len(result.items) == 0

    def test_collect_invalid_json(self) -> None:
        """Invalid JSON returns failed result."""
        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(body="not json")
        rate_limiter = MagicMock()

        collector = HuggingFaceDailyPapersCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert not result.success
        assert len(result.items) == 0

    def test_item_has_quality_signals(self) -> None:
        """Items include quality signal metadata."""
        api_response = json.dumps(
            [
                {
                    "paper": {
                        "id": "2301.00001",
                        "title": "Test Paper",
                        "summary": "Abstract text.",
                    },
                    "upvotes": 50,
                    "publishedAt": "2023-01-01T00:00:00Z",
                },
            ]
        )

        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(body=api_response)
        rate_limiter = MagicMock()

        collector = HuggingFaceDailyPapersCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert len(result.items) == 1
        raw_json = json.loads(result.items[0].raw_json)
        assert raw_json["from_hf_daily_papers"] is True
        assert raw_json["upvotes"] == 50
        assert raw_json["is_trending"] is True
        assert raw_json["arxiv_id"] == "2301.00001"

    def test_respects_max_items(self) -> None:
        """Collection respects max_items configuration."""
        papers = [
            {
                "paper": {"id": f"2301.0000{i}", "title": f"Paper {i}"},
                "upvotes": i,
                "publishedAt": "2023-01-01T00:00:00Z",
            }
            for i in range(20)
        ]
        api_response = json.dumps(papers)

        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(body=api_response)
        rate_limiter = MagicMock()

        collector = HuggingFaceDailyPapersCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()  # max_items=10
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert result.success
        assert len(result.items) == 10
