"""Unit tests for configuration constants."""

import pytest

from src.features.config.constants import (
    COMPONENT_CLI,
    COMPONENT_CONFIG,
    COMPONENT_EVIDENCE,
    FEATURE_KEY,
    FILE_TYPE_ENTITIES,
    FILE_TYPE_SOURCES,
    FILE_TYPE_TOPICS,
    STATUS_P1_DONE,
    STATUS_P2_E2E_PASSED,
    STATUS_P3_REFACTORED,
    STATUS_READY,
    VALID_URL_SCHEMES,
    VALIDATION_FAILED,
    VALIDATION_PASSED,
)


class TestStatusConstants:
    """Tests for status constants."""

    @pytest.mark.unit
    def test_status_values_are_unique(self) -> None:
        """Test that all status values are unique."""
        statuses = [
            STATUS_P1_DONE,
            STATUS_P2_E2E_PASSED,
            STATUS_P3_REFACTORED,
            STATUS_READY,
        ]
        assert len(statuses) == len(set(statuses))

    @pytest.mark.unit
    def test_status_values_are_non_empty(self) -> None:
        """Test that all status values are non-empty strings."""
        statuses = [
            STATUS_P1_DONE,
            STATUS_P2_E2E_PASSED,
            STATUS_P3_REFACTORED,
            STATUS_READY,
        ]
        for status in statuses:
            assert isinstance(status, str)
            assert len(status) > 0


class TestValidationConstants:
    """Tests for validation result constants."""

    @pytest.mark.unit
    def test_validation_results_are_strings(self) -> None:
        """Test that validation results are strings."""
        assert isinstance(VALIDATION_PASSED, str)
        assert isinstance(VALIDATION_FAILED, str)

    @pytest.mark.unit
    def test_validation_results_are_different(self) -> None:
        """Test that passed and failed are different."""
        assert VALIDATION_PASSED != VALIDATION_FAILED


class TestComponentConstants:
    """Tests for component name constants."""

    @pytest.mark.unit
    def test_component_names_are_lowercase(self) -> None:
        """Test that component names are lowercase."""
        components = [COMPONENT_CONFIG, COMPONENT_CLI, COMPONENT_EVIDENCE]
        for component in components:
            assert component == component.lower()


class TestFeatureKeyConstant:
    """Tests for feature key constant."""

    @pytest.mark.unit
    def test_feature_key_format(self) -> None:
        """Test that feature key follows expected format."""
        assert isinstance(FEATURE_KEY, str)
        # Should be kebab-case
        assert "-" in FEATURE_KEY
        assert FEATURE_KEY.lower() == FEATURE_KEY


class TestUrlSchemeConstants:
    """Tests for URL scheme constants."""

    @pytest.mark.unit
    def test_valid_schemes_are_tuple(self) -> None:
        """Test that valid schemes is a tuple for startswith()."""
        assert isinstance(VALID_URL_SCHEMES, tuple)

    @pytest.mark.unit
    def test_valid_schemes_include_http_and_https(self) -> None:
        """Test that both HTTP and HTTPS are valid."""
        assert "http://" in VALID_URL_SCHEMES
        assert "https://" in VALID_URL_SCHEMES


class TestFileTypeConstants:
    """Tests for file type constants."""

    @pytest.mark.unit
    def test_file_types_are_unique(self) -> None:
        """Test that file types are unique."""
        types = [FILE_TYPE_SOURCES, FILE_TYPE_ENTITIES, FILE_TYPE_TOPICS]
        assert len(types) == len(set(types))
