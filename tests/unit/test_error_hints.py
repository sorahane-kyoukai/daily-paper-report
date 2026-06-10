"""Unit tests for error hints system."""

import pytest

from src.features.config.error_hints import (
    ERROR_HINTS,
    FIELD_HINTS,
    format_validation_error,
    get_error_hint,
)


class TestGetErrorHint:
    """Tests for get_error_hint function."""

    @pytest.mark.unit
    def test_returns_hint_for_known_error_type(self) -> None:
        """Test that known error types return their hints."""
        hint = get_error_hint("missing")
        assert hint == ERROR_HINTS["missing"]
        assert "required" in hint.lower()

    @pytest.mark.unit
    def test_returns_hint_for_enum_error(self) -> None:
        """Test hint for enum validation errors."""
        hint = get_error_hint("enum")
        assert "allowed values" in hint.lower()

    @pytest.mark.unit
    def test_returns_default_for_unknown_error_type(self) -> None:
        """Test that unknown error types return default hint."""
        hint = get_error_hint("some_unknown_error_type")
        assert "documentation" in hint.lower()

    @pytest.mark.unit
    def test_field_specific_hint_takes_precedence(self) -> None:
        """Test that field-specific hints override error type hints."""
        # 'tier' has a specific hint in FIELD_HINTS
        hint = get_error_hint("enum", field_name="sources.0.tier")
        assert hint == FIELD_HINTS["tier"]
        assert "0" in hint and "1" in hint and "2" in hint

    @pytest.mark.unit
    def test_extracts_simple_field_name_from_path(self) -> None:
        """Test that field name is extracted from dotted path."""
        hint = get_error_hint("missing", field_name="entities.3.keywords")
        assert hint == FIELD_HINTS["keywords"]

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("field_name", "expected_substring"),
        [
            ("id", "lowercase"),
            ("url", "HTTP"),
            ("tier", "priority"),
            ("method", "rss_atom"),
            ("kind", "blog"),
            ("region", "cn"),
            ("keywords", "non-empty"),
            ("max_items", "1000"),
        ],
    )
    def test_field_hints_contain_expected_info(
        self, field_name: str, expected_substring: str
    ) -> None:
        """Test that field hints contain relevant information."""
        hint = get_error_hint("missing", field_name=field_name)
        assert expected_substring.lower() in hint.lower() or expected_substring in hint


class TestFormatValidationError:
    """Tests for format_validation_error function."""

    @pytest.mark.unit
    def test_formats_error_with_hint(self) -> None:
        """Test error formatting with hint included."""
        formatted = format_validation_error(
            location="sources.0.url",
            message="Field required",
            error_type="missing",
            include_hint=True,
        )
        assert "sources.0.url" in formatted
        assert "Field required" in formatted
        assert "Hint:" in formatted

    @pytest.mark.unit
    def test_formats_error_without_hint(self) -> None:
        """Test error formatting without hint."""
        formatted = format_validation_error(
            location="sources.0.url",
            message="Field required",
            error_type="missing",
            include_hint=False,
        )
        assert "sources.0.url" in formatted
        assert "Field required" in formatted
        assert "Hint:" not in formatted

    @pytest.mark.unit
    def test_uses_field_specific_hint_when_available(self) -> None:
        """Test that field-specific hints are used in formatting."""
        formatted = format_validation_error(
            location="sources.1.tier",
            message="Input should be 0, 1 or 2",
            error_type="enum",
            include_hint=True,
        )
        # Should use the tier-specific hint
        assert "priority" in formatted.lower()


class TestErrorHintsCompleteness:
    """Tests to ensure error hints are comprehensive."""

    @pytest.mark.unit
    def test_common_pydantic_error_types_have_hints(self) -> None:
        """Test that common Pydantic error types have hints."""
        common_types = [
            "missing",
            "enum",
            "int_type",
            "string_type",
            "value_error",
        ]
        for error_type in common_types:
            assert error_type in ERROR_HINTS, f"Missing hint for {error_type}"

    @pytest.mark.unit
    def test_key_fields_have_specific_hints(self) -> None:
        """Test that key configuration fields have specific hints."""
        key_fields = ["id", "url", "tier", "method", "kind", "region"]
        for field in key_fields:
            assert field in FIELD_HINTS, f"Missing hint for field {field}"
