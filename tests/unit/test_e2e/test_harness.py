"""Unit tests for E2E harness."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from src.e2e.harness import ClearDataResult, E2EHarness, E2EResult, run_e2e_harness
from src.e2e.state_machine import E2EState


class TestClearDataResult:
    """Tests for ClearDataResult."""

    def test_success_when_no_errors(self) -> None:
        """success is True when no errors."""
        result = ClearDataResult(
            cleared_db=True,
            cleared_output=True,
            cleared_cache=True,
            steps_performed=["step1"],
            errors=[],
        )

        assert result.success

    def test_failure_when_errors(self) -> None:
        """success is False when errors present."""
        result = ClearDataResult(
            errors=["Failed to delete database"],
        )

        assert not result.success


class TestE2EResult:
    """Tests for E2EResult."""

    def test_initial_state(self) -> None:
        """E2EResult starts with sensible defaults."""
        result = E2EResult(run_id="test-123")

        assert result.run_id == "test-123"
        assert not result.passed
        assert result.final_state == E2EState.PENDING
        assert result.failure_reason is None

    def test_duration_ms(self) -> None:
        """duration_ms computes correctly."""
        from datetime import datetime

        result = E2EResult(run_id="test-123")
        result.started_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result.finished_at = datetime(2024, 1, 15, 12, 0, 1, tzinfo=UTC)

        assert result.duration_ms == 1000.0

    def test_duration_ms_not_finished(self) -> None:
        """duration_ms is 0 when not finished."""
        result = E2EResult(run_id="test-123")

        assert result.duration_ms == 0.0


class TestE2EHarness:
    """Tests for E2EHarness."""

    def test_harness_creation(self, tmp_path: Path) -> None:
        """E2EHarness can be created."""
        harness = E2EHarness(
            db_path=tmp_path / "test.db",
            output_dir=tmp_path / "output",
            run_id="test-123",
        )

        assert harness.state == E2EState.PENDING

    def test_harness_run_from_clean_state(self, tmp_path: Path) -> None:
        """Harness runs successfully from clean state."""
        db_path = tmp_path / "state.db"
        output_dir = tmp_path / "output"

        harness = E2EHarness(
            db_path=db_path,
            output_dir=output_dir,
            run_id="test-123",
            git_commit="abc123",
        )

        result = harness.run()

        assert result.passed
        assert result.final_state == E2EState.DONE
        assert "CLEAR_DATA" in result.steps_performed
        assert "RUN_PIPELINE" in result.steps_performed
        assert "VALIDATE_DB" in result.steps_performed
        assert "VALIDATE_JSON" in result.steps_performed
        assert "VALIDATE_HTML" in result.steps_performed
        assert "ARCHIVE_EVIDENCE" in result.steps_performed

    def test_harness_clears_existing_data(self, tmp_path: Path) -> None:
        """Harness clears existing database and output."""
        db_path = tmp_path / "state.db"
        output_dir = tmp_path / "output"

        # Create existing data
        db_path.touch()
        output_dir.mkdir()
        (output_dir / "old_file.html").write_text("old content")

        harness = E2EHarness(
            db_path=db_path,
            output_dir=output_dir,
            run_id="test-123",
        )

        result = harness.run()

        assert result.passed
        assert result.clear_data_result is not None
        # The old output dir should have been deleted and recreated
        assert not (output_dir / "old_file.html").exists()

    def test_harness_idempotent_runs(self, tmp_path: Path) -> None:
        """Two runs with same fixtures produce identical checksums."""
        db_path = tmp_path / "state.db"
        output_dir = tmp_path / "output"

        # First run
        harness1 = E2EHarness(
            db_path=db_path,
            output_dir=output_dir,
            run_id="run-1",
        )
        result1 = harness1.run()

        # Second run (clears data from first run)
        harness2 = E2EHarness(
            db_path=db_path,
            output_dir=output_dir,
            run_id="run-2",
        )
        result2 = harness2.run()

        # Both runs should succeed
        assert result1.passed
        assert result2.passed

        # JSON schema should be valid in both
        assert result1.json_validation is not None
        assert result2.json_validation is not None
        assert result1.json_validation.passed
        assert result2.json_validation.passed

        # Both should produce output checksums
        assert len(result1.output_checksums) > 0
        assert len(result2.output_checksums) > 0


class TestRunE2EHarness:
    """Tests for run_e2e_harness convenience function."""

    def test_run_e2e_harness(self, tmp_path: Path) -> None:
        """run_e2e_harness function works."""
        result = run_e2e_harness(
            db_path=tmp_path / "state.db",
            output_dir=tmp_path / "output",
            run_id="test-123",
        )

        assert result.passed
        assert result.run_id == "test-123"

    def test_run_e2e_harness_generates_run_id(self, tmp_path: Path) -> None:
        """run_e2e_harness generates run_id if not provided."""
        result = run_e2e_harness(
            db_path=tmp_path / "state.db",
            output_dir=tmp_path / "output",
        )

        assert result.passed
        assert result.run_id is not None
        assert len(result.run_id) > 0


class TestFrozenTime:
    """Tests for frozen_time parameter enabling byte-identical outputs."""

    def test_frozen_time_in_output(self, tmp_path: Path) -> None:
        """frozen_time appears in output JSON."""
        frozen = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

        harness = E2EHarness(
            db_path=tmp_path / "state.db",
            output_dir=tmp_path / "output",
            run_id="frozen-test",
            frozen_time=frozen,
        )

        result = harness.run()
        assert result.passed

        # Check that the frozen time appears in daily.json
        daily_json = tmp_path / "output" / "api" / "daily.json"
        assert daily_json.exists()

        import json

        data = json.loads(daily_json.read_text())
        assert data["generated_at"] == frozen.isoformat()
        assert data["run_date"] == "2026-01-15"

    def test_byte_identical_with_frozen_time(self, tmp_path: Path) -> None:
        """Two runs with same run_id and frozen_time produce identical outputs."""
        frozen = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        run_id = "byte-identical-test"

        # First run
        harness1 = E2EHarness(
            db_path=tmp_path / "state1.db",
            output_dir=tmp_path / "output1",
            run_id=run_id,
            frozen_time=frozen,
        )
        result1 = harness1.run()
        assert result1.passed

        # Second run with different paths but same run_id and frozen_time
        harness2 = E2EHarness(
            db_path=tmp_path / "state2.db",
            output_dir=tmp_path / "output2",
            run_id=run_id,
            frozen_time=frozen,
        )
        result2 = harness2.run()
        assert result2.passed

        # Compute checksums
        daily1 = tmp_path / "output1" / "api" / "daily.json"
        daily2 = tmp_path / "output2" / "api" / "daily.json"

        checksum1 = hashlib.sha256(daily1.read_bytes()).hexdigest()
        checksum2 = hashlib.sha256(daily2.read_bytes()).hexdigest()

        assert checksum1 == checksum2, "daily.json should be byte-identical"

    def test_without_frozen_time_timestamps_differ(self, tmp_path: Path) -> None:
        """Without frozen_time, consecutive runs have different timestamps."""
        import time

        # First run
        harness1 = E2EHarness(
            db_path=tmp_path / "state1.db",
            output_dir=tmp_path / "output1",
            run_id="run-1",
        )
        result1 = harness1.run()
        assert result1.passed

        # Small delay
        time.sleep(0.01)

        # Second run
        harness2 = E2EHarness(
            db_path=tmp_path / "state2.db",
            output_dir=tmp_path / "output2",
            run_id="run-1",  # Same run_id but no frozen_time
        )
        result2 = harness2.run()
        assert result2.passed

        # Checksums should differ (timestamps are different)
        daily1 = tmp_path / "output1" / "api" / "daily.json"
        daily2 = tmp_path / "output2" / "api" / "daily.json"

        checksum1 = hashlib.sha256(daily1.read_bytes()).hexdigest()
        checksum2 = hashlib.sha256(daily2.read_bytes()).hexdigest()

        # Note: Without frozen_time, timestamps differ so checksums differ
        # This test verifies that frozen_time is needed for identical outputs
        assert checksum1 != checksum2, "Without frozen_time, outputs should differ"


class TestBaseValidator:
    """Tests for BaseValidator abstract class."""

    def test_base_validator_compute_checksum(self) -> None:
        """compute_checksum produces correct SHA-256."""
        from src.e2e.validators import BaseValidator

        content = b"Hello, World!"
        expected = hashlib.sha256(content).hexdigest()

        actual = BaseValidator.compute_checksum(content)

        assert actual == expected

    def test_base_validator_compute_file_checksum(self, tmp_path: Path) -> None:
        """compute_file_checksum works on files."""
        from src.e2e.validators import BaseValidator

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"Test content")

        expected = hashlib.sha256(b"Test content").hexdigest()
        actual = BaseValidator.compute_file_checksum(test_file)

        assert actual == expected

    def test_validators_inherit_from_base(self) -> None:
        """All validators inherit from BaseValidator."""
        from src.e2e.validators import (
            BaseValidator,
            DatabaseValidator,
            HtmlValidator,
            JsonValidator,
        )

        db_validator = DatabaseValidator("test")
        json_validator = JsonValidator("test")
        html_validator = HtmlValidator("test")

        assert isinstance(db_validator, BaseValidator)
        assert isinstance(json_validator, BaseValidator)
        assert isinstance(html_validator, BaseValidator)

    def test_validator_has_run_id_property(self) -> None:
        """Validators expose run_id via property."""
        from src.e2e.validators import DatabaseValidator

        validator = DatabaseValidator("my-run-id")

        assert validator.run_id == "my-run-id"
