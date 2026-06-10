"""Unit tests for evidence state machine."""

import pytest

from src.features.evidence.state_machine import (
    EvidenceState,
    EvidenceStateError,
    EvidenceStateMachine,
)


class TestEvidenceState:
    """Tests for EvidenceState enum."""

    def test_states_exist(self) -> None:
        """All required states should exist."""
        assert EvidenceState.EVIDENCE_PENDING is not None
        assert EvidenceState.EVIDENCE_WRITING is not None
        assert EvidenceState.EVIDENCE_DONE is not None
        assert EvidenceState.EVIDENCE_FAILED is not None

    def test_states_are_unique(self) -> None:
        """Each state should have a unique value."""
        values = [s.value for s in EvidenceState]
        assert len(values) == len(set(values))


class TestEvidenceStateMachine:
    """Tests for EvidenceStateMachine class."""

    def test_initial_state_is_pending(self) -> None:
        """State machine should start in EVIDENCE_PENDING state."""
        sm = EvidenceStateMachine(run_id="test-run")
        assert sm.state == EvidenceState.EVIDENCE_PENDING

    def test_run_id_is_stored(self) -> None:
        """Run ID should be accessible."""
        sm = EvidenceStateMachine(run_id="my-run-id")
        assert sm.run_id == "my-run-id"

    def test_valid_transition_pending_to_writing(self) -> None:
        """Should allow transition from PENDING to WRITING."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        assert sm.state == EvidenceState.EVIDENCE_WRITING

    def test_valid_transition_pending_to_failed(self) -> None:
        """Should allow transition from PENDING to FAILED."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_FAILED)
        assert sm.state == EvidenceState.EVIDENCE_FAILED

    def test_valid_transition_writing_to_done(self) -> None:
        """Should allow transition from WRITING to DONE."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        sm.transition(EvidenceState.EVIDENCE_DONE)
        assert sm.state == EvidenceState.EVIDENCE_DONE

    def test_valid_transition_writing_to_failed(self) -> None:
        """Should allow transition from WRITING to FAILED."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        sm.transition(EvidenceState.EVIDENCE_FAILED)
        assert sm.state == EvidenceState.EVIDENCE_FAILED

    def test_invalid_transition_pending_to_done(self) -> None:
        """Should not allow direct transition from PENDING to DONE."""
        sm = EvidenceStateMachine(run_id="test")
        with pytest.raises(EvidenceStateError) as exc_info:
            sm.transition(EvidenceState.EVIDENCE_DONE)
        assert exc_info.value.from_state == EvidenceState.EVIDENCE_PENDING
        assert exc_info.value.to_state == EvidenceState.EVIDENCE_DONE

    def test_invalid_transition_from_done(self) -> None:
        """Should not allow any transition from DONE (terminal state)."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        sm.transition(EvidenceState.EVIDENCE_DONE)
        with pytest.raises(EvidenceStateError):
            sm.transition(EvidenceState.EVIDENCE_FAILED)

    def test_invalid_transition_from_failed(self) -> None:
        """Should not allow any transition from FAILED (terminal state)."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_FAILED)
        with pytest.raises(EvidenceStateError):
            sm.transition(EvidenceState.EVIDENCE_DONE)

    def test_can_transition_returns_true_for_valid(self) -> None:
        """can_transition should return True for valid transitions."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.can_transition(EvidenceState.EVIDENCE_WRITING) is True
        assert sm.can_transition(EvidenceState.EVIDENCE_FAILED) is True

    def test_can_transition_returns_false_for_invalid(self) -> None:
        """can_transition should return False for invalid transitions."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.can_transition(EvidenceState.EVIDENCE_DONE) is False

    def test_is_terminal_for_done(self) -> None:
        """is_terminal should return True for DONE state."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        sm.transition(EvidenceState.EVIDENCE_DONE)
        assert sm.is_terminal() is True

    def test_is_terminal_for_failed(self) -> None:
        """is_terminal should return True for FAILED state."""
        sm = EvidenceStateMachine(run_id="test")
        sm.transition(EvidenceState.EVIDENCE_FAILED)
        assert sm.is_terminal() is True

    def test_is_terminal_for_pending(self) -> None:
        """is_terminal should return False for PENDING state."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.is_terminal() is False

    def test_is_done(self) -> None:
        """is_done should return True only in DONE state."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.is_done() is False
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        assert sm.is_done() is False
        sm.transition(EvidenceState.EVIDENCE_DONE)
        assert sm.is_done() is True

    def test_is_failed(self) -> None:
        """is_failed should return True only in FAILED state."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.is_failed() is False
        sm.transition(EvidenceState.EVIDENCE_FAILED)
        assert sm.is_failed() is True

    def test_is_pending(self) -> None:
        """is_pending should return True only in PENDING state."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.is_pending() is True
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        assert sm.is_pending() is False

    def test_is_writing(self) -> None:
        """is_writing should return True only in WRITING state."""
        sm = EvidenceStateMachine(run_id="test")
        assert sm.is_writing() is False
        sm.transition(EvidenceState.EVIDENCE_WRITING)
        assert sm.is_writing() is True


class TestEvidenceStateError:
    """Tests for EvidenceStateError exception."""

    def test_error_message(self) -> None:
        """Error should have descriptive message."""
        error = EvidenceStateError(
            EvidenceState.EVIDENCE_PENDING, EvidenceState.EVIDENCE_DONE
        )
        assert "EVIDENCE_PENDING" in str(error)
        assert "EVIDENCE_DONE" in str(error)
        assert "Invalid" in str(error)

    def test_error_stores_states(self) -> None:
        """Error should store from and to states."""
        error = EvidenceStateError(
            EvidenceState.EVIDENCE_PENDING, EvidenceState.EVIDENCE_DONE
        )
        assert error.from_state == EvidenceState.EVIDENCE_PENDING
        assert error.to_state == EvidenceState.EVIDENCE_DONE
