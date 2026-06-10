"""Unit tests for collector error types."""

import pytest
from pydantic import ValidationError

from src.collectors.errors import (
    CollectorError,
    CollectorErrorClass,
    ErrorRecord,
    ParseError,
    SchemaError,
)


class TestCollectorErrorClass:
    """Tests for CollectorErrorClass enum."""

    def test_all_classes_defined(self) -> None:
        """Verify all error classes are defined."""
        assert CollectorErrorClass.FETCH == "FETCH"
        assert CollectorErrorClass.PARSE == "PARSE"
        assert CollectorErrorClass.SCHEMA == "SCHEMA"

    def test_class_count(self) -> None:
        """Verify exactly 3 error classes exist."""
        assert len(CollectorErrorClass) == 3


class TestCollectorError:
    """Tests for base CollectorError."""

    def test_basic_error(self) -> None:
        """Create a basic collector error."""
        error = CollectorError(
            error_class=CollectorErrorClass.FETCH,
            message="Connection failed",
        )
        assert error.error_class == CollectorErrorClass.FETCH
        assert error.message == "Connection failed"
        assert error.source_id is None
        assert error.details == {}

    def test_error_with_source_id(self) -> None:
        """Error includes source ID."""
        error = CollectorError(
            error_class=CollectorErrorClass.PARSE,
            message="Invalid XML",
            source_id="my-source",
        )
        assert error.source_id == "my-source"

    def test_error_with_details(self) -> None:
        """Error includes details dict."""
        error = CollectorError(
            error_class=CollectorErrorClass.SCHEMA,
            message="Missing field",
            details={"field": "title", "expected": "string"},
        )
        assert error.details == {"field": "title", "expected": "string"}

    def test_error_to_dict(self) -> None:
        """Error can be serialized to dict."""
        error = CollectorError(
            error_class=CollectorErrorClass.FETCH,
            message="Timeout",
            source_id="source-1",
            details={"timeout": 30},
        )
        d = error.to_dict()
        assert d["error_class"] == "FETCH"
        assert d["message"] == "Timeout"
        assert d["source_id"] == "source-1"
        assert d["details"] == {"timeout": 30}

    def test_error_is_exception(self) -> None:
        """CollectorError is an Exception."""
        error = CollectorError(
            error_class=CollectorErrorClass.FETCH,
            message="Test error",
        )
        assert isinstance(error, Exception)
        assert str(error) == "Test error"


class TestParseError:
    """Tests for ParseError."""

    def test_parse_error_basic(self) -> None:
        """Create a basic parse error."""
        error = ParseError(message="Invalid XML syntax")
        assert error.error_class == CollectorErrorClass.PARSE
        assert error.message == "Invalid XML syntax"

    def test_parse_error_with_location(self) -> None:
        """Parse error includes line and column."""
        error = ParseError(
            message="Unexpected token",
            line=42,
            column=10,
        )
        assert error.line == 42
        assert error.column == 10
        assert error.details["line"] == 42
        assert error.details["column"] == 10

    def test_parse_error_with_context(self) -> None:
        """Parse error includes context snippet."""
        error = ParseError(
            message="Parse failed",
            context="<invalid>...</invalid>",
        )
        assert error.context == "<invalid>...</invalid>"
        assert error.details["context"] == "<invalid>...</invalid>"


class TestSchemaError:
    """Tests for SchemaError."""

    def test_schema_error_basic(self) -> None:
        """Create a basic schema error."""
        error = SchemaError(message="Validation failed")
        assert error.error_class == CollectorErrorClass.SCHEMA
        assert error.message == "Validation failed"

    def test_schema_error_with_field_info(self) -> None:
        """Schema error includes field information."""
        error = SchemaError(
            message="Invalid type",
            field="published_at",
            expected="datetime",
            actual="string",
        )
        assert error.field == "published_at"
        assert error.expected == "datetime"
        assert error.actual == "string"
        assert error.details["field"] == "published_at"
        assert error.details["expected"] == "datetime"
        assert error.details["actual"] == "string"


class TestErrorRecord:
    """Tests for ErrorRecord Pydantic model."""

    def test_create_from_dict(self) -> None:
        """Create ErrorRecord from dictionary."""
        record = ErrorRecord(
            error_class=CollectorErrorClass.FETCH,
            message="Connection error",
        )
        assert record.error_class == CollectorErrorClass.FETCH
        assert record.message == "Connection error"

    def test_create_from_exception(self) -> None:
        """Create ErrorRecord from CollectorError exception."""
        error = ParseError(
            message="Invalid format",
            source_id="source-1",
            line=10,
        )
        record = ErrorRecord.from_exception(error)
        assert record.error_class == CollectorErrorClass.PARSE
        assert record.message == "Invalid format"
        assert record.source_id == "source-1"
        assert record.details["line"] == 10

    def test_record_is_immutable(self) -> None:
        """ErrorRecord is frozen."""
        record = ErrorRecord(
            error_class=CollectorErrorClass.SCHEMA,
            message="Test",
        )
        with pytest.raises(ValidationError):
            record.message = "Changed"  # type: ignore[misc]
