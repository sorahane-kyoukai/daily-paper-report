"""Fixture loader for E2E harness with checksum computation.

Provides deterministic fixtures for all supported data sources:
- RSS/Atom feeds
- arXiv API Atom responses
- GitHub releases JSON
- HuggingFace model list JSON
- OpenReview responses
- HTML list pages
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import structlog


logger = structlog.get_logger()


@dataclass
class FixtureInfo:
    """Information about a loaded fixture.

    Attributes:
        name: Fixture name/identifier.
        path: Path to the fixture file.
        content: Fixture content as bytes.
        checksum: SHA-256 checksum of the content.
        source_type: Type of source this fixture represents.
    """

    name: str
    path: str
    content: bytes
    checksum: str
    source_type: str


@dataclass
class FixtureManifest:
    """Manifest of all loaded fixtures with checksums.

    Attributes:
        fixtures: Dictionary of fixture name to FixtureInfo.
        total_bytes: Total bytes across all fixtures.
        version: Fixture version string.
    """

    fixtures: dict[str, FixtureInfo] = field(default_factory=dict)
    total_bytes: int = 0
    version: str = "1.0.0"

    def add_fixture(self, fixture: FixtureInfo) -> None:
        """Add a fixture to the manifest.

        Args:
            fixture: Fixture information.
        """
        self.fixtures[fixture.name] = fixture
        self.total_bytes += len(fixture.content)

    def get_checksums(self) -> dict[str, str]:
        """Get all fixture checksums.

        Returns:
            Dictionary of fixture name to checksum.
        """
        return {name: f.checksum for name, f in sorted(self.fixtures.items())}

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "version": self.version,
            "total_bytes": self.total_bytes,
            "fixtures": [
                {
                    "name": f.name,
                    "path": f.path,
                    "checksum": f.checksum,
                    "bytes": len(f.content),
                    "source_type": f.source_type,
                }
                for f in sorted(self.fixtures.values(), key=lambda x: x.name)
            ],
        }


class FixtureLoader:
    """Loads and manages E2E test fixtures.

    Fixtures are loaded from the `tests/e2e_fixtures/` directory
    and mapped to source URLs for the mock HTTP transport.
    """

    # Source type to fixture subdirectory mapping
    SOURCE_TYPE_DIRS: ClassVar[dict[str, str]] = {
        "rss_atom": "rss_atom",
        "arxiv": "arxiv",
        "github": "github",
        "huggingface": "huggingface",
        "openreview": "openreview",
        "html_list": "html_list",
    }

    def __init__(
        self,
        fixtures_dir: Path | None = None,
        run_id: str = "fixture-loader",
    ) -> None:
        """Initialize the fixture loader.

        Args:
            fixtures_dir: Path to fixtures directory.
            run_id: Run ID for logging.
        """
        self._fixtures_dir = fixtures_dir or (
            Path(__file__).parent.parent.parent / "tests" / "e2e_fixtures"
        )
        self._run_id = run_id
        self._manifest = FixtureManifest()
        self._url_to_fixture: dict[str, FixtureInfo] = {}
        self._log = logger.bind(
            component="e2e",
            run_id=run_id,
        )

    @property
    def manifest(self) -> FixtureManifest:
        """Get the fixture manifest."""
        return self._manifest

    def load_all(self) -> FixtureManifest:
        """Load all fixtures from the fixtures directory.

        Returns:
            Manifest of loaded fixtures.
        """
        self._log.info(
            "loading_fixtures",
            fixtures_dir=str(self._fixtures_dir),
        )

        if not self._fixtures_dir.exists():
            self._log.warning(
                "fixtures_dir_not_found",
                fixtures_dir=str(self._fixtures_dir),
            )
            return self._manifest

        for source_type, subdir in self.SOURCE_TYPE_DIRS.items():
            type_dir = self._fixtures_dir / subdir
            if type_dir.exists():
                self._load_fixtures_from_dir(type_dir, source_type)

        self._log.info(
            "fixtures_loaded",
            count=len(self._manifest.fixtures),
            total_bytes=self._manifest.total_bytes,
        )

        return self._manifest

    def _load_fixtures_from_dir(self, dir_path: Path, source_type: str) -> None:
        """Load fixtures from a directory.

        Args:
            dir_path: Directory path.
            source_type: Type of source these fixtures represent.
        """
        for file_path in sorted(dir_path.iterdir()):
            if file_path.is_file() and not file_path.name.startswith("."):
                self._load_fixture(file_path, source_type)

    def _load_fixture(self, file_path: Path, source_type: str) -> None:
        """Load a single fixture file.

        Args:
            file_path: Path to fixture file.
            source_type: Type of source.
        """
        content = file_path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()

        fixture = FixtureInfo(
            name=file_path.stem,
            path=str(file_path.relative_to(self._fixtures_dir)),
            content=content,
            checksum=checksum,
            source_type=source_type,
        )

        self._manifest.add_fixture(fixture)

        self._log.debug(
            "fixture_loaded",
            name=fixture.name,
            source_type=source_type,
            bytes=len(content),
            checksum=checksum[:16],
        )

    def register_url_mapping(self, url: str, fixture_name: str) -> None:
        """Register a URL to fixture mapping.

        Args:
            url: URL that should return this fixture.
            fixture_name: Name of the fixture to return.

        Raises:
            KeyError: If fixture not found.
        """
        if fixture_name not in self._manifest.fixtures:
            raise KeyError(f"Fixture not found: {fixture_name}")

        self._url_to_fixture[url] = self._manifest.fixtures[fixture_name]

        self._log.debug(
            "url_mapping_registered",
            url=url,
            fixture=fixture_name,
        )

    def get_fixture_for_url(self, url: str) -> FixtureInfo | None:
        """Get fixture content for a URL.

        Args:
            url: URL to look up.

        Returns:
            FixtureInfo if mapped, None otherwise.
        """
        return self._url_to_fixture.get(url)

    def get_fixture(self, name: str) -> FixtureInfo | None:
        """Get a fixture by name.

        Args:
            name: Fixture name.

        Returns:
            FixtureInfo if found, None otherwise.
        """
        return self._manifest.fixtures.get(name)

    def save_manifest(self, output_path: Path) -> None:
        """Save the fixture manifest to a JSON file.

        Args:
            output_path: Path to write manifest to.
        """
        content = json.dumps(self._manifest.to_dict(), sort_keys=True, indent=2)
        output_path.write_text(content)

        self._log.info(
            "manifest_saved",
            path=str(output_path),
            fixtures_count=len(self._manifest.fixtures),
        )
