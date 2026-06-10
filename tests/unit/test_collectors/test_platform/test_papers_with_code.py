"""Unit tests for Papers With Code collector."""

import json
from unittest.mock import MagicMock

from src.collectors.platform.papers_with_code import (
    PapersWithCodeCollector,
    extract_arxiv_id,
)
from src.features.config.schemas.base import SourceKind, SourceMethod, SourceTier
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.models import FetchResult
from tests.helpers.time import FIXED_NOW


def _make_source_config() -> SourceConfig:
    """Create a test SourceConfig."""
    return SourceConfig(
        id="papers-with-code",
        name="Papers With Code",
        url="https://paperswithcode.com/api/v1/papers/",
        tier=SourceTier.TIER_0,
        method=SourceMethod.PAPERS_WITH_CODE,
        kind=SourceKind.PAPER,
        max_items=10,
    )


def _make_fetch_result(
    status_code: int = 200,
    body: str = "{}",
) -> FetchResult:
    """Create a test FetchResult."""
    return FetchResult(
        status_code=status_code,
        final_url="https://paperswithcode.com/api/v1/papers/",
        body_bytes=body.encode("utf-8"),
    )


class TestExtractArxivId:
    """Tests for extract_arxiv_id function."""

    def test_extract_from_arxiv_url(self) -> None:
        """Extract arXiv ID from arxiv URL."""
        arxiv_id = extract_arxiv_id(
            url="https://paperswithcode.com/paper/attention-is-all-you-need",
            arxiv_url="https://arxiv.org/abs/1706.03762",
        )
        assert arxiv_id == "1706.03762"

    def test_extract_from_main_url(self) -> None:
        """Extract arXiv ID when arxiv_url is None."""
        arxiv_id = extract_arxiv_id(
            url="https://arxiv.org/abs/2301.12345",
            arxiv_url=None,
        )
        assert arxiv_id == "2301.12345"

    def test_returns_none_for_non_arxiv(self) -> None:
        """Return None when no arXiv ID found."""
        arxiv_id = extract_arxiv_id(
            url="https://example.com/paper",
            arxiv_url=None,
        )
        assert arxiv_id is None


class TestPapersWithCodeCollector:
    """Tests for PapersWithCodeCollector class."""

    def test_collect_success(self) -> None:
        """Successful collection returns items."""
        api_response = json.dumps(
            {
                "results": [
                    {
                        "id": "attention-is-all-you-need",
                        "title": "Attention Is All You Need",
                        "url_abs": "https://arxiv.org/abs/1706.03762",
                        "published": "2017-06-12T00:00:00Z",
                        "authors": ["Ashish Vaswani", "Noam Shazeer"],
                        "repository_url": "https://github.com/tensorflow/tensor2tensor",
                    },
                    {
                        "id": "bert",
                        "title": "BERT",
                        "url_abs": "https://arxiv.org/abs/1810.04805",
                        "published": "2018-10-11T00:00:00Z",
                        "proceeding": "NAACL 2019",
                    },
                ]
            }
        )

        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(body=api_response)
        rate_limiter = MagicMock()

        collector = PapersWithCodeCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert result.success
        assert len(result.items) == 2
        assert result.items[0].title == "Attention Is All You Need"
        assert result.items[1].title == "BERT"

    def test_collect_api_error(self) -> None:
        """API error returns failed result."""
        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(
            status_code=500,
            body="Internal Server Error",
        )
        rate_limiter = MagicMock()

        collector = PapersWithCodeCollector(
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

        collector = PapersWithCodeCollector(
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
            {
                "results": [
                    {
                        "id": "test-paper",
                        "title": "Test Paper",
                        "url_abs": "https://arxiv.org/abs/2301.00001",
                        "repository_url": "https://github.com/test/repo",
                        "published": "2017-06-12T00:00:00Z",
                    },
                ]
            }
        )

        http_client = MagicMock()
        http_client.fetch.return_value = _make_fetch_result(body=api_response)
        rate_limiter = MagicMock()

        collector = PapersWithCodeCollector(
            run_id="test",
            rate_limiter=rate_limiter,
        )
        source_config = _make_source_config()
        now = FIXED_NOW

        result = collector.collect(source_config, http_client, now)

        assert len(result.items) == 1
        raw_json = json.loads(result.items[0].raw_json)
        assert raw_json["from_papers_with_code"] is True
        assert raw_json["has_code"] is True
        assert raw_json["arxiv_id"] == "2301.00001"
