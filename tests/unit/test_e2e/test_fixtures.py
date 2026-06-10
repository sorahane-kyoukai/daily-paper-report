"""Unit tests for fixture loader."""

import hashlib
from pathlib import Path
from typing import Any

import pytest

from src.e2e.fixtures import FixtureInfo, FixtureLoader, FixtureManifest


class TestFixtureInfo:
    """Tests for FixtureInfo dataclass."""

    def test_fixture_info_creation(self) -> None:
        """FixtureInfo can be created with all fields."""
        content = b"test content"
        checksum = hashlib.sha256(content).hexdigest()

        info = FixtureInfo(
            name="test_fixture",
            path="rss_atom/test_fixture.xml",
            content=content,
            checksum=checksum,
            source_type="rss_atom",
        )

        assert info.name == "test_fixture"
        assert info.path == "rss_atom/test_fixture.xml"
        assert info.content == content
        assert info.checksum == checksum
        assert info.source_type == "rss_atom"


class TestFixtureManifest:
    """Tests for FixtureManifest."""

    def test_empty_manifest(self) -> None:
        """Empty manifest has zero fixtures."""
        manifest = FixtureManifest()

        assert len(manifest.fixtures) == 0
        assert manifest.total_bytes == 0
        assert manifest.version == "1.0.0"

    def test_add_fixture(self) -> None:
        """Adding fixture updates manifest."""
        manifest = FixtureManifest()
        content = b"test content"

        fixture = FixtureInfo(
            name="test",
            path="test.xml",
            content=content,
            checksum="abc123",
            source_type="rss_atom",
        )

        manifest.add_fixture(fixture)

        assert len(manifest.fixtures) == 1
        assert manifest.total_bytes == len(content)
        assert "test" in manifest.fixtures

    def test_get_checksums(self) -> None:
        """get_checksums returns sorted dictionary."""
        manifest = FixtureManifest()

        manifest.add_fixture(FixtureInfo("z_fixture", "z.xml", b"z", "zzz", "rss_atom"))
        manifest.add_fixture(FixtureInfo("a_fixture", "a.xml", b"a", "aaa", "rss_atom"))

        checksums = manifest.get_checksums()

        assert list(checksums.keys()) == ["a_fixture", "z_fixture"]
        assert checksums["a_fixture"] == "aaa"
        assert checksums["z_fixture"] == "zzz"

    def test_to_dict(self) -> None:
        """to_dict produces valid dictionary."""
        manifest = FixtureManifest()
        manifest.add_fixture(
            FixtureInfo("test", "test.xml", b"content", "abc123", "rss_atom")
        )

        result = manifest.to_dict()

        assert result["version"] == "1.0.0"
        assert result["total_bytes"] == 7
        fixtures: list[dict[str, Any]] = result["fixtures"]  # type: ignore[assignment]
        assert len(fixtures) == 1
        assert fixtures[0]["name"] == "test"


class TestFixtureLoader:
    """Tests for FixtureLoader."""

    def test_loader_creation(self, tmp_path: Path) -> None:
        """FixtureLoader can be created."""
        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")

        assert loader.manifest is not None

    def test_load_from_nonexistent_dir(self, tmp_path: Path) -> None:
        """Loading from nonexistent directory returns empty manifest."""
        nonexistent = tmp_path / "nonexistent"
        loader = FixtureLoader(fixtures_dir=nonexistent, run_id="test-run")

        manifest = loader.load_all()

        assert len(manifest.fixtures) == 0

    def test_load_fixtures_from_directory(self, tmp_path: Path) -> None:
        """Loading fixtures from directory works."""
        # Create fixture subdirectory
        rss_dir = tmp_path / "rss_atom"
        rss_dir.mkdir()

        # Create fixture file
        content = b"<rss>test</rss>"
        (rss_dir / "test_feed.xml").write_bytes(content)

        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        manifest = loader.load_all()

        assert len(manifest.fixtures) == 1
        assert "test_feed" in manifest.fixtures
        assert manifest.fixtures["test_feed"].content == content
        assert manifest.fixtures["test_feed"].source_type == "rss_atom"

    def test_checksum_computation(self, tmp_path: Path) -> None:
        """Checksums are computed correctly."""
        rss_dir = tmp_path / "rss_atom"
        rss_dir.mkdir()

        content = b"test content for checksum"
        expected_checksum = hashlib.sha256(content).hexdigest()
        (rss_dir / "test.xml").write_bytes(content)

        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        manifest = loader.load_all()

        assert manifest.fixtures["test"].checksum == expected_checksum

    def test_register_url_mapping(self, tmp_path: Path) -> None:
        """URL mappings can be registered."""
        rss_dir = tmp_path / "rss_atom"
        rss_dir.mkdir()
        (rss_dir / "feed.xml").write_bytes(b"<rss></rss>")

        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        loader.load_all()
        loader.register_url_mapping("https://example.com/feed.rss", "feed")

        fixture = loader.get_fixture_for_url("https://example.com/feed.rss")

        assert fixture is not None
        assert fixture.name == "feed"

    def test_register_nonexistent_fixture_raises(self, tmp_path: Path) -> None:
        """Registering nonexistent fixture raises KeyError."""
        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        loader.load_all()

        with pytest.raises(KeyError):
            loader.register_url_mapping("https://example.com/feed", "nonexistent")

    def test_get_fixture_for_unregistered_url(self, tmp_path: Path) -> None:
        """Getting fixture for unregistered URL returns None."""
        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        loader.load_all()

        fixture = loader.get_fixture_for_url("https://unknown.com/feed")

        assert fixture is None

    def test_save_manifest(self, tmp_path: Path) -> None:
        """Manifest can be saved to JSON."""
        rss_dir = tmp_path / "rss_atom"
        rss_dir.mkdir()
        (rss_dir / "test.xml").write_bytes(b"<rss></rss>")

        loader = FixtureLoader(fixtures_dir=tmp_path, run_id="test-run")
        loader.load_all()

        output_path = tmp_path / "manifest.json"
        loader.save_manifest(output_path)

        assert output_path.exists()

        import json

        data = json.loads(output_path.read_text())
        assert "fixtures" in data
        assert "version" in data
