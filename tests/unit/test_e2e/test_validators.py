"""Unit tests for E2E validators."""

import json
import sqlite3
from pathlib import Path

from src.e2e.validators import DatabaseValidator, HtmlValidator, JsonValidator


class TestDatabaseValidator:
    """Tests for DatabaseValidator."""

    def test_validate_nonexistent_db(self, tmp_path: Path) -> None:
        """Validation fails for nonexistent database."""
        validator = DatabaseValidator("test-run")
        result = validator.validate(tmp_path / "nonexistent.db")

        assert not result.passed
        assert "not found" in result.message

    def test_validate_valid_db(self, tmp_path: Path) -> None:
        """Validation passes for valid database."""
        db_path = tmp_path / "test.db"

        # Create a valid database with expected schema
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER)")
        conn.execute("INSERT INTO schema_version VALUES (1)")
        conn.execute("CREATE TABLE runs (id INTEGER)")
        conn.execute("CREATE TABLE items (id INTEGER)")
        conn.execute("CREATE TABLE http_cache (id INTEGER)")
        conn.commit()
        conn.close()

        validator = DatabaseValidator("test-run")
        result = validator.validate(db_path)

        assert result.passed
        assert result.schema_version == 1
        assert "runs" in result.table_row_counts
        assert "items" in result.table_row_counts

    def test_validate_wrong_schema_version(self, tmp_path: Path) -> None:
        """Validation fails for wrong schema version."""
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER)")
        conn.execute("INSERT INTO schema_version VALUES (999)")
        conn.commit()
        conn.close()

        validator = DatabaseValidator("test-run")
        result = validator.validate(db_path)

        assert not result.passed
        assert "version mismatch" in result.message.lower()
        assert result.schema_version == 999

    def test_validate_missing_tables(self, tmp_path: Path) -> None:
        """Validation fails for missing required tables."""
        db_path = tmp_path / "test.db"

        from src.features.store.migrations import CURRENT_VERSION

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER)")
        conn.execute("INSERT INTO schema_version VALUES (?)", (CURRENT_VERSION,))
        conn.execute("CREATE TABLE runs (id INTEGER)")
        # Missing items and http_cache
        conn.commit()
        conn.close()

        validator = DatabaseValidator("test-run")
        result = validator.validate(db_path)

        assert not result.passed
        assert "missing" in result.message.lower()


class TestJsonValidator:
    """Tests for JsonValidator."""

    def test_validate_nonexistent_file(self, tmp_path: Path) -> None:
        """Validation fails for nonexistent file."""
        validator = JsonValidator("test-run")
        result = validator.validate(tmp_path / "nonexistent.json")

        assert not result.passed
        assert "not found" in result.message

    def test_validate_valid_json(self, tmp_path: Path) -> None:
        """Validation passes for valid daily.json."""
        json_path = tmp_path / "daily.json"
        data = {
            "run_id": "test-123",
            "run_date": "2024-01-15",
            "generated_at": "2024-01-15T12:00:00Z",
            "top5": [{"story_id": "s1"}],
            "model_releases_by_entity": {"org1": []},
            "papers": [],
            "radar": [],
        }
        json_path.write_text(json.dumps(data))

        validator = JsonValidator("test-run")
        result = validator.validate(json_path)

        assert result.passed
        assert result.checksum is not None
        assert "top5" in result.sections_present
        assert "papers" in result.sections_present

    def test_validate_missing_sections(self, tmp_path: Path) -> None:
        """Validation fails for missing required sections."""
        json_path = tmp_path / "daily.json"
        data = {
            "run_id": "test-123",
            # Missing other required sections
        }
        json_path.write_text(json.dumps(data))

        validator = JsonValidator("test-run")
        result = validator.validate(json_path)

        assert not result.passed
        assert "missing" in result.message.lower()

    def test_validate_invalid_json(self, tmp_path: Path) -> None:
        """Validation fails for invalid JSON."""
        json_path = tmp_path / "daily.json"
        json_path.write_text("{ invalid json }")

        validator = JsonValidator("test-run")
        result = validator.validate(json_path)

        assert not result.passed
        assert "invalid json" in result.message.lower()

    def test_validate_wrong_section_types(self, tmp_path: Path) -> None:
        """Validation fails for wrong section types."""
        json_path = tmp_path / "daily.json"
        data = {
            "run_id": "test-123",
            "run_date": "2024-01-15",
            "generated_at": "2024-01-15T12:00:00Z",
            "top5": "not a list",  # Should be a list
            "model_releases_by_entity": {},
            "papers": [],
            "radar": [],
        }
        json_path.write_text(json.dumps(data))

        validator = JsonValidator("test-run")
        result = validator.validate(json_path)

        assert not result.passed
        assert "top5" in result.message.lower()


class TestHtmlValidator:
    """Tests for HtmlValidator."""

    def test_validate_nonexistent_dir(self, tmp_path: Path) -> None:
        """Validation fails for nonexistent directory."""
        validator = HtmlValidator("test-run")
        result = validator.validate(tmp_path / "nonexistent")

        assert not result.passed
        assert "not found" in result.message

    def test_validate_with_required_files(self, tmp_path: Path) -> None:
        """Validation passes when required files exist."""
        (tmp_path / "index.html").write_text("<html></html>")

        validator = HtmlValidator("test-run")
        result = validator.validate(tmp_path)

        assert result.passed
        assert "index.html" in result.files_found
        assert "index.html" in result.checksums
        assert len(result.files_missing) == 0

    def test_validate_missing_required_files(self, tmp_path: Path) -> None:
        """Validation fails when required files missing."""
        # Create empty output directory (no index.html)
        validator = HtmlValidator("test-run")
        result = validator.validate(tmp_path)

        assert not result.passed
        assert "index.html" in result.files_missing

    def test_discovers_all_html_files(self, tmp_path: Path) -> None:
        """Validator discovers all HTML files including subdirectories."""
        (tmp_path / "index.html").write_text("<html></html>")
        subdir = tmp_path / "pages"
        subdir.mkdir()
        (subdir / "about.html").write_text("<html></html>")
        (subdir / "contact.html").write_text("<html></html>")

        validator = HtmlValidator("test-run")
        result = validator.validate(tmp_path)

        assert result.passed
        assert len(result.files_found) == 3
        assert "pages/about.html" in result.files_found
        assert "pages/contact.html" in result.files_found

    def test_computes_checksums(self, tmp_path: Path) -> None:
        """Validator computes checksums for all files."""
        content = "<html><head></head><body>Test</body></html>"
        (tmp_path / "index.html").write_text(content)

        validator = HtmlValidator("test-run")
        result = validator.validate(tmp_path)

        assert result.passed
        assert len(result.checksums) == 1
        assert len(result.checksums["index.html"]) == 64  # SHA-256 hex length
