"""Unit tests for CollectorRunner method registration."""

from unittest.mock import MagicMock

from src.collectors.arxiv.api import ArxivApiCollector
from src.collectors.runner import CollectorRunner
from src.features.config.schemas.base import SourceMethod
from src.features.store.store import StateStore


def _make_runner() -> CollectorRunner:
    """Create a CollectorRunner with mocked dependencies."""
    mock_store = MagicMock(spec=StateStore)
    mock_http = MagicMock()
    return CollectorRunner(
        store=mock_store,
        http_client=mock_http,
        run_id="test",
        max_workers=1,
    )


# Methods that are intentionally not collected (no collector implementation)
_UNCOLLECTED_METHODS = {
    SourceMethod.HTML_SINGLE,
    SourceMethod.STATUS_ONLY,
}


class TestMethodRegistration:
    """Regression tests for collector registration in CollectorRunner."""

    def test_arxiv_api_registered(self) -> None:
        """ARXIV_API method must be registered (regression for silent skip bug)."""
        runner = _make_runner()
        assert SourceMethod.ARXIV_API in runner._collectors

    def test_arxiv_api_collector_type(self) -> None:
        """ARXIV_API must use ArxivApiCollector."""
        runner = _make_runner()
        assert isinstance(runner._collectors[SourceMethod.ARXIV_API], ArxivApiCollector)

    def test_all_collectable_methods_registered(self) -> None:
        """Every SourceMethod with a collector must be registered."""
        runner = _make_runner()
        supported = set(runner.get_supported_methods())

        for method in SourceMethod:
            if method in _UNCOLLECTED_METHODS:
                continue
            assert method in supported, (
                f"SourceMethod.{method.name} is not registered in CollectorRunner. "
                f"If this method has a collector, add it to runner._collectors."
            )

    def test_supported_methods_count(self) -> None:
        """Runner should support 8 collection methods."""
        runner = _make_runner()
        # RSS_ATOM, ARXIV_API, HTML_LIST, GITHUB_RELEASES,
        # HF_ORG, OPENREVIEW_VENUE, PAPERS_WITH_CODE, HF_DAILY_PAPERS
        assert len(runner.get_supported_methods()) == 8
