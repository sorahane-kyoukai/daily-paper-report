"""Error types for the collector framework."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CollectorErrorClass(str, Enum):
    """Classification of collector errors.

    - FETCH: HTTP/network errors during fetch
    - PARSE: Errors parsing response content
    - SCHEMA: Data doesn't match expected schema
    """

    FETCH = "FETCH"
    PARSE = "PARSE"
    SCHEMA = "SCHEMA"


class CollectorError(Exception):
    """Base exception for collector errors.

    Provides structured error information for logging and status reporting.
    """

    def __init__(
        self,
        error_class: CollectorErrorClass,
        message: str,
        source_id: str | None = None,
        details: dict[str, str | int | bool | None] | None = None,
    ) -> None:
        """Initialize the collector error.

        Args:
            error_class: Classification of the error.
            message: Human-readable error message.
            source_id: Identifier of the source that failed.
            details: Additional structured error details.
        """
        super().__init__(message)
        self.error_class = error_class
        self.message = message
        self.source_id = source_id
        self.details = details or {}

    def to_dict(
        self,
    ) -> dict[str, str | int | bool | None | dict[str, str | int | bool | None]]:
        """Convert error to dictionary for logging/serialization.

        Returns:
            Dictionary representation of the error.
        """
        return {
            "error_class": self.error_class.value,
            "message": self.message,
            "source_id": self.source_id,
            "details": self.details,
        }


class ParseError(CollectorError):
    """Error parsing content from a source.

    Raised when content cannot be parsed (malformed XML, invalid HTML, etc.).
    """

    def __init__(
        self,
        message: str,
        source_id: str | None = None,
        line: int | None = None,
        column: int | None = None,
        context: str | None = None,
    ) -> None:
        """Initialize the parse error.

        Args:
            message: Human-readable error message.
            source_id: Identifier of the source that failed.
            line: Line number where parsing failed.
            column: Column number where parsing failed.
            context: Snippet of content around the error.
        """
        details: dict[str, str | int | bool | None] = {}
        if line is not None:
            details["line"] = line
        if column is not None:
            details["column"] = column
        if context is not None:
            details["context"] = context

        super().__init__(
            error_class=CollectorErrorClass.PARSE,
            message=message,
            source_id=source_id,
            details=details,
        )
        self.line = line
        self.column = column
        self.context = context


class SchemaError(CollectorError):
    """Error when data doesn't match expected schema.

    Raised when required fields are missing or have invalid types.
    """

    def __init__(
        self,
        message: str,
        source_id: str | None = None,
        field: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        """Initialize the schema error.

        Args:
            message: Human-readable error message.
            source_id: Identifier of the source that failed.
            field: Name of the field with the error.
            expected: Expected type or value.
            actual: Actual type or value found.
        """
        details: dict[str, str | int | bool | None] = {}
        if field is not None:
            details["field"] = field
        if expected is not None:
            details["expected"] = expected
        if actual is not None:
            details["actual"] = actual

        super().__init__(
            error_class=CollectorErrorClass.SCHEMA,
            message=message,
            source_id=source_id,
            details=details,
        )
        self.field = field
        self.expected = expected
        self.actual = actual


class ErrorRecord(BaseModel):
    """Serializable error record for persistence and reporting.

    Used to store errors in the run status table and sources status page.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_class: CollectorErrorClass = Field(description="Error classification")
    message: Annotated[str, Field(min_length=1, description="Error message")]
    source_id: str | None = Field(default=None, description="Source identifier")
    details: dict[str, str | int | bool | None] = Field(
        default_factory=dict, description="Additional error details"
    )

    @classmethod
    def from_exception(cls, error: CollectorError) -> "ErrorRecord":
        """Create an ErrorRecord from a CollectorError exception.

        Args:
            error: The exception to convert.

        Returns:
            ErrorRecord instance.
        """
        return cls(
            error_class=error.error_class,
            message=error.message,
            source_id=error.source_id,
            details=error.details,
        )
