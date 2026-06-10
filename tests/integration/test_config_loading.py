"""Integration tests for configuration loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.features.config.loader import ConfigLoader
from src.features.config.state_machine import ConfigState


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "config"


class TestConfigLoaderIntegration:
    """Integration tests for ConfigLoader."""

    @pytest.mark.integration
    def test_load_valid_configs(self) -> None:
        """Test loading valid configuration files."""
        loader = ConfigLoader(run_id="test-run-001")

        effective = loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        assert loader.state == ConfigState.READY
        assert len(effective.sources.sources) == 63
        assert len(effective.entities.entities) == 36
        assert len(effective.topics.topics) == 27

    @pytest.mark.integration
    def test_load_produces_checksums(self) -> None:
        """Test that loading produces file checksums."""
        loader = ConfigLoader(run_id="test-run-002")

        loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        checksums = loader.file_checksums
        assert len(checksums) == 3
        for path, checksum in checksums.items():
            assert len(checksum) == 64  # SHA-256 hex length
            assert path.endswith(".yaml")

    @pytest.mark.integration
    def test_load_validation_duration_recorded(self) -> None:
        """Test that validation duration is recorded."""
        loader = ConfigLoader(run_id="test-run-003")

        loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        assert loader.validation_duration_ms > 0

    @pytest.mark.integration
    def test_load_invalid_config_fails(self) -> None:
        """Test that loading invalid config fails."""
        loader = ConfigLoader(run_id="test-run-004")

        with pytest.raises(ValidationError):
            loader.load(
                sources_path=FIXTURES_DIR / "invalid_sources.yaml",
                entities_path=FIXTURES_DIR / "entities.yaml",
                topics_path=FIXTURES_DIR / "topics.yaml",
            )

        assert loader.state == ConfigState.FAILED
        assert len(loader.validation_errors) > 0

    @pytest.mark.integration
    def test_load_missing_file_fails(self) -> None:
        """Test that loading missing file fails."""
        loader = ConfigLoader(run_id="test-run-005")

        with pytest.raises(FileNotFoundError):
            loader.load(
                sources_path=FIXTURES_DIR / "nonexistent.yaml",
                entities_path=FIXTURES_DIR / "entities.yaml",
                topics_path=FIXTURES_DIR / "topics.yaml",
            )

        assert loader.state == ConfigState.FAILED

    @pytest.mark.integration
    def test_validation_summary(self) -> None:
        """Test validation summary content."""
        loader = ConfigLoader(run_id="test-run-006")

        loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        summary = loader.get_validation_summary()
        assert summary["run_id"] == "test-run-006"
        assert summary["state"] == "READY"
        assert summary["validation_error_count"] == 0
        assert len(summary["file_checksums"]) == 3  # type: ignore[arg-type]

    @pytest.mark.integration
    def test_validation_summary_json_stable(self) -> None:
        """Test that validation summary JSON is stable."""
        loader = ConfigLoader(run_id="test-run-007")

        loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        json1 = loader.get_validation_summary_json()
        json2 = loader.get_validation_summary_json()
        assert json1 == json2


class TestConfigIdempotency:
    """Tests for configuration loading idempotency."""

    @pytest.mark.integration
    def test_repeated_loads_produce_identical_configs(self) -> None:
        """Test that repeated loads produce identical configurations."""
        loader1 = ConfigLoader(run_id="test-run-idempotent-1")
        loader2 = ConfigLoader(run_id="test-run-idempotent-1")

        config1 = loader1.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        config2 = loader2.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        # Byte-identical normalized JSON
        assert config1.to_normalized_json() == config2.to_normalized_json()

        # Identical checksums
        assert config1.compute_checksum() == config2.compute_checksum()

    @pytest.mark.integration
    def test_file_checksums_stable(self) -> None:
        """Test that file checksums are stable across loads."""
        loader1 = ConfigLoader(run_id="test-run-checksum-1")
        loader2 = ConfigLoader(run_id="test-run-checksum-2")

        loader1.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        loader2.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        # File checksums should be identical
        for path1, checksum1 in loader1.file_checksums.items():
            # Find matching path in loader2
            matching_paths = [
                p for p in loader2.file_checksums if Path(p).name == Path(path1).name
            ]
            assert len(matching_paths) == 1
            assert loader2.file_checksums[matching_paths[0]] == checksum1


class TestEffectiveConfigIntegration:
    """Integration tests for EffectiveConfig with real files."""

    @pytest.mark.integration
    def test_effective_config_summary(self) -> None:
        """Test effective config summary from real files."""
        loader = ConfigLoader(run_id="test-run-summary")

        config = loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        summary = config.summary()
        assert summary["sources_count"] == 63
        assert summary["entities_count"] == 36
        assert summary["topics_count"] == 27
        assert "config_checksum" in summary

    @pytest.mark.integration
    def test_get_enabled_sources_from_file(self) -> None:
        """Test get_enabled_sources with real file data."""
        loader = ConfigLoader(run_id="test-run-enabled")

        config = loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        enabled = config.get_enabled_sources()
        # Enabled sources in fixture
        assert len(enabled) == 56

    @pytest.mark.integration
    def test_get_entities_by_region_from_file(self) -> None:
        """Test get_entities_by_region with real file data."""
        loader = ConfigLoader(run_id="test-run-region")

        config = loader.load(
            sources_path=FIXTURES_DIR / "sources.yaml",
            entities_path=FIXTURES_DIR / "entities.yaml",
            topics_path=FIXTURES_DIR / "topics.yaml",
        )

        intl_entities = config.get_entities_by_region("intl")
        cn_entities = config.get_entities_by_region("cn")

        assert len(intl_entities) == 33
        assert len(cn_entities) == 3
