"""Unit tests for ranker state machine."""

import pytest

from src.ranker.state_machine import (
    RankerState,
    RankerStateMachine,
    RankerStateTransitionError,
)


class TestRankerState:
    """Tests for RankerState enum."""

    def test_all_states_exist(self) -> None:
        """Verify all required states exist."""
        assert RankerState.STORIES_FINAL.value == "STORIES_FINAL"
        assert RankerState.SCORED.value == "SCORED"
        assert RankerState.QUOTA_FILTERED.value == "QUOTA_FILTERED"
        assert RankerState.ORDERED_OUTPUTS.value == "ORDERED_OUTPUTS"

    def test_state_count(self) -> None:
        """Verify there are exactly 4 states."""
        assert len(RankerState) == 4


class TestRankerStateMachine:
    """Tests for RankerStateMachine."""

    def test_initial_state(self) -> None:
        """State machine starts in STORIES_FINAL."""
        sm = RankerStateMachine(run_id="test-run")
        assert sm.state == RankerState.STORIES_FINAL
        assert sm.run_id == "test-run"

    def test_valid_transition_stories_final_to_scored(self) -> None:
        """STORIES_FINAL -> SCORED is valid."""
        sm = RankerStateMachine(run_id="test-run")
        sm.to_scored()
        assert sm.state == RankerState.SCORED

    def test_valid_transition_scored_to_quota_filtered(self) -> None:
        """SCORED -> QUOTA_FILTERED is valid."""
        sm = RankerStateMachine(run_id="test-run")
        sm.to_scored()
        sm.to_quota_filtered()
        assert sm.state == RankerState.QUOTA_FILTERED

    def test_valid_transition_quota_filtered_to_ordered_outputs(self) -> None:
        """QUOTA_FILTERED -> ORDERED_OUTPUTS is valid."""
        sm = RankerStateMachine(run_id="test-run")
        sm.to_scored()
        sm.to_quota_filtered()
        sm.to_ordered_outputs()
        assert sm.state == RankerState.ORDERED_OUTPUTS

    def test_full_lifecycle(self) -> None:
        """Complete state machine lifecycle."""
        sm = RankerStateMachine(run_id="test-run")

        assert not sm.is_terminal
        sm.to_scored()

        assert not sm.is_terminal
        sm.to_quota_filtered()

        assert not sm.is_terminal
        sm.to_ordered_outputs()

        assert sm.is_terminal

    def test_invalid_transition_stories_final_to_quota_filtered(self) -> None:
        """STORIES_FINAL -> QUOTA_FILTERED is invalid (skip SCORED)."""
        sm = RankerStateMachine(run_id="test-run")

        with pytest.raises(RankerStateTransitionError) as exc_info:
            sm.to_quota_filtered()

        assert exc_info.value.run_id == "test-run"
        assert exc_info.value.from_state == RankerState.STORIES_FINAL
        assert exc_info.value.to_state == RankerState.QUOTA_FILTERED

    def test_invalid_transition_stories_final_to_ordered_outputs(self) -> None:
        """STORIES_FINAL -> ORDERED_OUTPUTS is invalid (skip states)."""
        sm = RankerStateMachine(run_id="test-run")

        with pytest.raises(RankerStateTransitionError):
            sm.to_ordered_outputs()

    def test_invalid_transition_scored_to_ordered_outputs(self) -> None:
        """SCORED -> ORDERED_OUTPUTS is invalid (skip QUOTA_FILTERED)."""
        sm = RankerStateMachine(run_id="test-run")
        sm.to_scored()

        with pytest.raises(RankerStateTransitionError):
            sm.to_ordered_outputs()

    def test_terminal_state_no_transitions(self) -> None:
        """No transitions allowed from ORDERED_OUTPUTS."""
        sm = RankerStateMachine(run_id="test-run")
        sm.to_scored()
        sm.to_quota_filtered()
        sm.to_ordered_outputs()

        assert sm.is_terminal

        # All transitions should fail
        with pytest.raises(RankerStateTransitionError):
            sm.to_scored()

        with pytest.raises(RankerStateTransitionError):
            sm.to_quota_filtered()

        with pytest.raises(RankerStateTransitionError):
            sm.to_ordered_outputs()

    def test_can_transition_to(self) -> None:
        """Test can_transition_to helper."""
        sm = RankerStateMachine(run_id="test-run")

        assert sm.can_transition_to(RankerState.SCORED)
        assert not sm.can_transition_to(RankerState.QUOTA_FILTERED)
        assert not sm.can_transition_to(RankerState.ORDERED_OUTPUTS)

    def test_custom_initial_state(self) -> None:
        """Can start from a specific state."""
        sm = RankerStateMachine(
            run_id="test-run",
            initial_state=RankerState.SCORED,
        )
        assert sm.state == RankerState.SCORED
        sm.to_quota_filtered()
        # After state transition, mypy incorrectly narrows state type
        assert sm.state == RankerState.QUOTA_FILTERED  # type: ignore[comparison-overlap]


class TestRankerStateTransitionError:
    """Tests for RankerStateTransitionError."""

    def test_error_message(self) -> None:
        """Error message includes context."""
        error = RankerStateTransitionError(
            run_id="test-123",
            from_state=RankerState.STORIES_FINAL,
            to_state=RankerState.ORDERED_OUTPUTS,
        )

        assert "test-123" in str(error)
        assert "STORIES_FINAL" in str(error)
        assert "ORDERED_OUTPUTS" in str(error)
        assert error.run_id == "test-123"
        assert error.from_state == RankerState.STORIES_FINAL
        assert error.to_state == RankerState.ORDERED_OUTPUTS
