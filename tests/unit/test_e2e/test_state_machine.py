"""Unit tests for E2E state machine."""

import pytest

from src.e2e.state_machine import (
    E2EState,
    E2EStateMachine,
    E2EStateTransitionError,
)


class TestE2EState:
    """Tests for E2EState enum."""

    def test_all_states_defined(self) -> None:
        """All expected states are defined."""
        expected_states = [
            "PENDING",
            "CLEAR_DATA",
            "RUN_PIPELINE",
            "VALIDATE_DB",
            "VALIDATE_JSON",
            "VALIDATE_HTML",
            "ARCHIVE_EVIDENCE",
            "DONE",
            "FAILED",
        ]
        actual_states = [s.name for s in E2EState]
        assert sorted(actual_states) == sorted(expected_states)


class TestE2EStateMachine:
    """Tests for E2EStateMachine."""

    def test_initial_state_is_pending(self) -> None:
        """State machine starts in PENDING state."""
        sm = E2EStateMachine("test-run")
        assert sm.state == E2EState.PENDING
        assert sm.is_pending()

    def test_valid_transitions(self) -> None:
        """Valid transitions succeed."""
        sm = E2EStateMachine("test-run")

        # Follow happy path
        sm.transition(E2EState.CLEAR_DATA)
        assert sm.state == E2EState.CLEAR_DATA

        sm.transition(E2EState.RUN_PIPELINE)
        # After state transition, mypy incorrectly narrows state type
        assert sm.state == E2EState.RUN_PIPELINE  # type: ignore[comparison-overlap]

        sm.transition(E2EState.VALIDATE_DB)
        assert sm.state == E2EState.VALIDATE_DB

        sm.transition(E2EState.VALIDATE_JSON)
        assert sm.state == E2EState.VALIDATE_JSON

        sm.transition(E2EState.VALIDATE_HTML)
        assert sm.state == E2EState.VALIDATE_HTML

        sm.transition(E2EState.ARCHIVE_EVIDENCE)
        assert sm.state == E2EState.ARCHIVE_EVIDENCE

        sm.transition(E2EState.DONE)
        assert sm.state == E2EState.DONE
        assert sm.is_done()

    def test_invalid_transition_raises_error(self) -> None:
        """Invalid transitions raise E2EStateTransitionError."""
        sm = E2EStateMachine("test-run")

        # Cannot skip states
        with pytest.raises(E2EStateTransitionError) as exc_info:
            sm.transition(E2EState.RUN_PIPELINE)

        assert exc_info.value.from_state == E2EState.PENDING
        assert exc_info.value.to_state == E2EState.RUN_PIPELINE

    def test_fail_from_any_state(self) -> None:
        """Can transition to FAILED from any non-terminal state."""
        sm = E2EStateMachine("test-run")
        sm.transition(E2EState.CLEAR_DATA)
        sm.fail("Test failure")

        assert sm.is_failed()
        assert sm.state == E2EState.FAILED

    def test_fail_from_terminal_state_is_noop(self) -> None:
        """Failing from terminal state does not raise."""
        sm = E2EStateMachine("test-run")

        # Get to DONE state
        sm.transition(E2EState.CLEAR_DATA)
        sm.transition(E2EState.RUN_PIPELINE)
        sm.transition(E2EState.VALIDATE_DB)
        sm.transition(E2EState.VALIDATE_JSON)
        sm.transition(E2EState.VALIDATE_HTML)
        sm.transition(E2EState.ARCHIVE_EVIDENCE)
        sm.transition(E2EState.DONE)

        # Fail should not raise
        sm.fail("Late failure")
        assert sm.state == E2EState.DONE  # State unchanged

    def test_is_terminal(self) -> None:
        """is_terminal returns True for DONE and FAILED."""
        sm = E2EStateMachine("test-run")
        assert not sm.is_terminal()

        sm.fail("test")
        assert sm.is_terminal()

    def test_can_transition(self) -> None:
        """can_transition checks validity."""
        sm = E2EStateMachine("test-run")

        assert sm.can_transition(E2EState.CLEAR_DATA)
        assert sm.can_transition(E2EState.FAILED)
        assert not sm.can_transition(E2EState.RUN_PIPELINE)
        assert not sm.can_transition(E2EState.DONE)

    def test_get_expected_next_state(self) -> None:
        """get_expected_next_state returns next state in sequence."""
        sm = E2EStateMachine("test-run")

        assert sm.get_expected_next_state() == E2EState.CLEAR_DATA

        sm.transition(E2EState.CLEAR_DATA)
        assert sm.get_expected_next_state() == E2EState.RUN_PIPELINE

        sm.transition(E2EState.RUN_PIPELINE)
        assert sm.get_expected_next_state() == E2EState.VALIDATE_DB

    def test_terminal_state_has_no_next(self) -> None:
        """Terminal states return None for next state."""
        sm = E2EStateMachine("test-run")
        sm.fail("test")

        assert sm.get_expected_next_state() is None
