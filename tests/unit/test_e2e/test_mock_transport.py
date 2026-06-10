"""Unit tests for mock HTTP transport."""

from pathlib import Path

import pytest

from src.e2e.fixtures import FixtureLoader
from src.e2e.mock_transport import MockHttpClient, NetworkAccessBlockedError


class TestMockHttpClient:
    """Tests for MockHttpClient."""

    @pytest.fixture
    def fixture_loader(self, tmp_path: Path) -> FixtureLoader:
        """Create a fixture loader with test fixtures."""
        rss_dir = tmp_path / "rss_atom"
        rss_dir.mkdir()
        (rss_dir / "test_feed.xml").write_bytes(b"<rss>test</rss>")

        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        loader.load_all()
        return loader

    def test_fetch_registered_url(self, fixture_loader: FixtureLoader) -> None:
        """Fetching registered URL returns fixture content."""
        fixture_loader.register_url_mapping("https://example.com/feed.rss", "test_feed")

        client = MockHttpClient(
            fixture_loader=fixture_loader,
            run_id="test-run",
        )

        result = client.fetch("source-1", "https://example.com/feed.rss")

        assert result.status_code == 200
        assert result.body_bytes == b"<rss>test</rss>"
        assert result.error is None
        assert "x-e2e-fixture" in result.headers

    def test_fetch_unregistered_url_blocked(
        self, fixture_loader: FixtureLoader
    ) -> None:
        """Fetching unregistered URL raises NetworkAccessBlockedError."""
        client = MockHttpClient(
            fixture_loader=fixture_loader,
            run_id="test-run",
            allow_unmatched=False,
        )

        with pytest.raises(NetworkAccessBlockedError) as exc_info:
            client.fetch("source-1", "https://unknown.com/feed")

        assert exc_info.value.url == "https://unknown.com/feed"

    def test_fetch_unregistered_url_allowed(
        self, fixture_loader: FixtureLoader
    ) -> None:
        """Fetching unregistered URL with allow_unmatched returns 404."""
        client = MockHttpClient(
            fixture_loader=fixture_loader,
            run_id="test-run",
            allow_unmatched=True,
        )

        result = client.fetch("source-1", "https://unknown.com/feed")

        assert result.status_code == 404
        assert result.error is not None

    def test_stats_tracking(self, fixture_loader: FixtureLoader) -> None:
        """Stats are tracked correctly."""
        fixture_loader.register_url_mapping("https://example.com/feed.rss", "test_feed")

        client = MockHttpClient(
            fixture_loader=fixture_loader,
            run_id="test-run",
            allow_unmatched=True,
        )

        # Matched request
        client.fetch("source-1", "https://example.com/feed.rss")
        # Unmatched request
        client.fetch("source-2", "https://unknown.com/feed")

        stats = client.stats
        assert stats.requests_total == 2
        assert stats.requests_matched == 1
        assert stats.requests_blocked == 1

    def test_request_log(self, fixture_loader: FixtureLoader) -> None:
        """Request log records all requests."""
        fixture_loader.register_url_mapping("https://example.com/feed.rss", "test_feed")

        client = MockHttpClient(
            fixture_loader=fixture_loader,
            run_id="test-run",
            allow_unmatched=True,
        )

        client.fetch("source-1", "https://example.com/feed.rss")

        log = client.get_request_log()
        assert len(log) == 1
        assert log[0]["url"] == "https://example.com/feed.rss"
        assert log[0]["source_id"] == "source-1"
        assert log[0]["fixture_name"] == "test_feed"
        assert log[0]["blocked"] is False

    def test_content_type_detection(self, tmp_path: Path) -> None:
        """Content type is detected from file extension."""
        # Create fixtures with different extensions
        rss_dir = tmp_path / "rss_atom"
        rss_dir.mkdir()
        (rss_dir / "feed.xml").write_bytes(b"<xml>")

        github_dir = tmp_path / "github"
        github_dir.mkdir()
        (github_dir / "releases.json").write_bytes(b"[]")

        html_dir = tmp_path / "html_list"
        html_dir.mkdir()
        (html_dir / "page.html").write_bytes(b"<html>")

        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        loader.load_all()
        loader.register_url_mapping("https://example.com/feed.xml", "feed")
        loader.register_url_mapping("https://example.com/releases.json", "releases")
        loader.register_url_mapping("https://example.com/page.html", "page")

        client = MockHttpClient(fixture_loader=loader, run_id="test-run")

        xml_result = client.fetch("s1", "https://example.com/feed.xml")
        json_result = client.fetch("s2", "https://example.com/releases.json")
        html_result = client.fetch("s3", "https://example.com/page.html")

        assert "xml" in xml_result.headers["content-type"]
        assert "json" in json_result.headers["content-type"]
        assert "html" in html_result.headers["content-type"]


class TestNetworkAccessBlockedError:
    """Tests for NetworkAccessBlockedError."""

    def test_error_message(self) -> None:
        """Error message includes URL."""
        error = NetworkAccessBlockedError("https://blocked.com/path")

        assert "https://blocked.com/path" in str(error)
        assert error.url == "https://blocked.com/path"
