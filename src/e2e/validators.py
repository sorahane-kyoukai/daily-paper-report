"""Schema validators for E2E harness output validation.

Provides validators for:
- SQLite database schema version
- daily.json schema validation
- Required HTML file presence

Design:
- BaseValidator defines common interface (ISP)
- Concrete validators implement specific validation logic
- ValidationResult hierarchy for typed results (LSP)
"""

import hashlib
import json
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import structlog

from src.features.store.migrations import CURRENT_VERSION as EXPECTED_SCHEMA_VERSION


logger = structlog.get_logger()

# Type variable for validator result types
T = TypeVar("T", bound="ValidationResult")


@dataclass
class ValidationResult:
    """Result of a validation check.

    Attributes:
        passed: Whether validation passed.
        message: Human-readable result message.
        details: Additional validation details.
    """

    passed: bool
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class DatabaseValidationResult(ValidationResult):
    """Result of database validation.

    Attributes:
        schema_version: Actual schema version found.
        table_row_counts: Row counts by table.
    """

    schema_version: int | None = None
    table_row_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class JsonValidationResult(ValidationResult):
    """Result of JSON validation.

    Attributes:
        checksum: SHA-256 checksum of the JSON file.
        sections_present: List of sections found in the JSON.
    """

    checksum: str | None = None
    sections_present: list[str] = field(default_factory=list)


@dataclass
class HtmlValidationResult(ValidationResult):
    """Result of HTML validation.

    Attributes:
        files_found: List of HTML files found.
        files_missing: List of required files that are missing.
        checksums: Map of file path to checksum.
    """

    files_found: list[str] = field(default_factory=list)
    files_missing: list[str] = field(default_factory=list)
    checksums: dict[str, str] = field(default_factory=dict)


class BaseValidator(ABC):
    """Abstract base class for E2E validators (ISP).

    Provides common interface and utility methods for all validators.
    Concrete validators must implement the validate() method.
    """

    def __init__(self, run_id: str) -> None:
        """Initialize the validator.

        Args:
            run_id: Run ID for logging context.
        """
        self._run_id = run_id
        self._log = logger.bind(
            component="e2e",
            run_id=run_id,
        )

    @property
    def run_id(self) -> str:
        """Get the run ID."""
        return self._run_id

    @abstractmethod
    def validate(self, path: Path) -> ValidationResult:
        """Validate the target path.

        Args:
            path: Path to validate (file or directory).

        Returns:
            ValidationResult with validation status.
        """

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        """Compute SHA-256 checksum of content.

        Args:
            content: Raw bytes to hash.

        Returns:
            Hexadecimal checksum string.
        """
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def compute_file_checksum(file_path: Path) -> str:
        """Compute SHA-256 checksum of a file.

        Args:
            file_path: Path to file.

        Returns:
            Hexadecimal checksum string.
        """
        return BaseValidator.compute_checksum(file_path.read_bytes())

    def _log_validation_start(self, target: str, path: Path) -> None:
        """Log validation start.

        Args:
            target: What is being validated (e.g., "database", "json").
            path: Path being validated.
        """
        self._log.info(f"validating_{target}", path=str(path))

    def _log_validation_passed(self, target: str, **kwargs: object) -> None:
        """Log validation success.

        Args:
            target: What was validated.
            **kwargs: Additional log context.
        """
        self._log.info(f"{target}_validation_passed", **kwargs)


class DatabaseValidator(BaseValidator):
    """Validates SQLite database schema and content."""

    # Required tables for a valid database
    REQUIRED_TABLES = ["runs", "items", "http_cache"]

    def validate(self, db_path: Path) -> DatabaseValidationResult:
        """Validate the database.

        Args:
            db_path: Path to SQLite database.

        Returns:
            DatabaseValidationResult with validation status.
        """
        self._log.info("validating_database", db_path=str(db_path))

        if not db_path.exists():
            return DatabaseValidationResult(
                passed=False,
                message=f"Database file not found: {db_path}",
            )

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Check schema version
            schema_version = self._get_schema_version(conn)
            if schema_version != EXPECTED_SCHEMA_VERSION:
                return DatabaseValidationResult(
                    passed=False,
                    message=(
                        f"Schema version mismatch: expected {EXPECTED_SCHEMA_VERSION}, "
                        f"got {schema_version}"
                    ),
                    schema_version=schema_version,
                )

            # Check tables exist
            table_counts = self._get_table_counts(conn)
            missing_tables = [t for t in self.REQUIRED_TABLES if t not in table_counts]
            if missing_tables:
                return DatabaseValidationResult(
                    passed=False,
                    message=f"Missing required tables: {missing_tables}",
                    schema_version=schema_version,
                    table_row_counts=table_counts,
                )

            conn.close()

            self._log.info(
                "database_validation_passed",
                schema_version=schema_version,
                table_counts=table_counts,
            )

            return DatabaseValidationResult(
                passed=True,
                message="Database validation passed",
                schema_version=schema_version,
                table_row_counts=table_counts,
                details={"db_path": str(db_path)},
            )

        except sqlite3.Error as e:
            return DatabaseValidationResult(
                passed=False,
                message=f"Database error: {e}",
            )

    def _get_schema_version(self, conn: sqlite3.Connection) -> int:
        """Get schema version from database.

        Args:
            conn: Database connection.

        Returns:
            Schema version number.
        """
        cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        return int(row["version"]) if row else 0

    def _get_table_counts(self, conn: sqlite3.Connection) -> dict[str, int]:
        """Get row counts for all tables.

        Args:
            conn: Database connection.

        Returns:
            Dictionary of table name to row count.
        """
        counts: dict[str, int] = {}
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
        valid_table_re = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
        for row in cursor.fetchall():
            table_name: str = row["name"]
            if not re.match(valid_table_re, table_name):
                continue
            count_cursor = conn.execute(  # nosemgrep: formatted-sql-query
                f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
            )
            counts[table_name] = count_cursor.fetchone()[0]
        return counts


class JsonValidator(BaseValidator):
    """Validates daily.json schema and content."""

    # Required top-level sections in daily.json
    REQUIRED_SECTIONS = [
        "run_id",
        "run_date",
        "generated_at",
        "top5",
        "model_releases_by_entity",
        "papers",
        "radar",
    ]

    def validate(self, json_path: Path) -> JsonValidationResult:
        """Validate the daily.json file.

        Args:
            json_path: Path to daily.json.

        Returns:
            JsonValidationResult with validation status.
        """
        self._log.info("validating_json", json_path=str(json_path))

        if not json_path.exists():
            return JsonValidationResult(
                passed=False,
                message=f"JSON file not found: {json_path}",
            )

        try:
            content = json_path.read_bytes()
            checksum = self.compute_checksum(content)
            data = json.loads(content)

            # Check required sections
            sections_present = [k for k in self.REQUIRED_SECTIONS if k in data]
            sections_missing = [k for k in self.REQUIRED_SECTIONS if k not in data]

            if sections_missing:
                return JsonValidationResult(
                    passed=False,
                    message=f"Missing required sections: {sections_missing}",
                    checksum=checksum,
                    sections_present=sections_present,
                )

            # Validate section types
            validation_errors = self._validate_section_types(data)
            if validation_errors:
                return JsonValidationResult(
                    passed=False,
                    message=f"Section type validation failed: {validation_errors}",
                    checksum=checksum,
                    sections_present=sections_present,
                )

            self._log.info(
                "json_validation_passed",
                checksum=checksum[:16],
                sections_count=len(sections_present),
            )

            return JsonValidationResult(
                passed=True,
                message="JSON validation passed",
                checksum=checksum,
                sections_present=sections_present,
                details={
                    "top5_count": len(data.get("top5", [])),
                    "papers_count": len(data.get("papers", [])),
                    "radar_count": len(data.get("radar", [])),
                    "model_releases_entities": list(
                        data.get("model_releases_by_entity", {}).keys()
                    ),
                },
            )

        except json.JSONDecodeError as e:
            return JsonValidationResult(
                passed=False,
                message=f"Invalid JSON: {e}",
            )

    def _validate_section_types(self, data: dict[str, object]) -> list[str]:
        """Validate types of required sections.

        Args:
            data: Parsed JSON data.

        Returns:
            List of validation error messages.
        """
        # top5, papers, radar should be lists
        errors = [
            f"{section} should be a list"
            for section in ["top5", "papers", "radar"]
            if section in data and not isinstance(data[section], list)
        ]

        # model_releases_by_entity should be a dict
        if "model_releases_by_entity" in data and not isinstance(
            data["model_releases_by_entity"], dict
        ):
            errors.append("model_releases_by_entity should be a dict")

        return errors


class HtmlValidator(BaseValidator):
    """Validates required HTML files presence and checksums."""

    # Required HTML files
    REQUIRED_FILES = ["index.html"]

    def validate(self, output_dir: Path) -> HtmlValidationResult:
        """Validate HTML files in output directory.

        Args:
            output_dir: Output directory.

        Returns:
            HtmlValidationResult with validation status.
        """
        self._log.info("validating_html", output_dir=str(output_dir))

        if not output_dir.exists():
            return HtmlValidationResult(
                passed=False,
                message=f"Output directory not found: {output_dir}",
            )

        files_found: list[str] = []
        files_missing: list[str] = []
        checksums: dict[str, str] = {}

        # Check required files
        for required_file in self.REQUIRED_FILES:
            file_path = output_dir / required_file
            if file_path.exists():
                files_found.append(required_file)
                checksums[required_file] = self.compute_file_checksum(file_path)
            else:
                files_missing.append(required_file)

        # Find all HTML files
        for html_file in output_dir.glob("**/*.html"):
            rel_path = str(html_file.relative_to(output_dir))
            if rel_path not in files_found:
                files_found.append(rel_path)
                checksums[rel_path] = self.compute_file_checksum(html_file)

        if files_missing:
            return HtmlValidationResult(
                passed=False,
                message=f"Missing required HTML files: {files_missing}",
                files_found=files_found,
                files_missing=files_missing,
                checksums=checksums,
            )

        self._log.info(
            "html_validation_passed",
            files_count=len(files_found),
        )

        return HtmlValidationResult(
            passed=True,
            message="HTML validation passed",
            files_found=files_found,
            files_missing=[],
            checksums=checksums,
        )
