"""Unit tests for Linker state machine."""

import pytest

from src.linker.state_machine import (
    LinkerState,
    LinkerStateMachine,
    LinkerStateTransitionError,
)


class TestLinkerState:
    """Tests for LinkerState enum."""

    def test_all_states_defined(self) -> None:
        """Test all required states are defined."""
        assert LinkerState.ITEMS_READY.value == "ITEMS_READY"
        assert LinkerState.ENTITY_TAGGED.value == "ENTITY_TAGGED"
        assert LinkerState.CANDIDATE_GROUPED.value == "CANDIDATE_GROUPED"
        assert LinkerState.STORIES_MERGED.value == "STORIES_MERGED"
        assert LinkerState.STORIES_FINAL.value == "STORIES_FINAL"


class TestLinkerStateMachine:
    """Tests for LinkerStateMachine class."""

    def test_initial_state(self) -> None:
        """Test initial state is ITEMS_READY."""
        sm = LinkerStateMachine(run_id="test-run")
        assert sm.state == LinkerState.ITEMS_READY

    def test_custom_initial_state(self) -> None:
        """Test custom initial state."""
        sm = LinkerStateMachine(
            run_id="test-run",
            initial_state=LinkerState.ENTITY_TAGGED,
        )
        assert sm.state == LinkerState.ENTITY_TAGGED

    def test_run_id_property(self) -> None:
        """Test run_id property."""
        sm = LinkerStateMachine(run_id="my-run-123")
        assert sm.run_id == "my-run-123"

    def test_is_terminal_false(self) -> None:
        """Test is_terminal is false for non-terminal states."""
        sm = LinkerStateMachine(run_id="test")
        assert not sm.is_terminal

    def test_is_terminal_true(self) -> None:
        """Test is_terminal is true for STORIES_FINAL."""
        sm = LinkerStateMachine(
            run_id="test",
            initial_state=LinkerState.STORIES_FINAL,
        )
        assert sm.is_terminal

    def test_valid_transition_items_to_entity(self) -> None:
        """Test valid transition from ITEMS_READY to ENTITY_TAGGED."""
        sm = LinkerStateMachine(run_id="test")
        assert sm.can_transition_to(LinkerState.ENTITY_TAGGED)
        sm.to_entity_tagged()
        assert sm.state == LinkerState.ENTITY_TAGGED

    def test_valid_transition_entity_to_grouped(self) -> None:
        """Test valid transition from ENTITY_TAGGED to CANDIDATE_GROUPED."""
        sm = LinkerStateMachine(
            run_id="test",
            initial_state=LinkerState.ENTITY_TAGGED,
        )
        assert sm.can_transition_to(LinkerState.CANDIDATE_GROUPED)
        sm.to_candidate_grouped()
        assert sm.state == LinkerState.CANDIDATE_GROUPED

    def test_valid_transition_grouped_to_merged(self) -> None:
        """Test valid transition from CANDIDATE_GROUPED to STORIES_MERGED."""
        sm = LinkerStateMachine(
            run_id="test",
            initial_state=LinkerState.CANDIDATE_GROUPED,
        )
        assert sm.can_transition_to(LinkerState.STORIES_MERGED)
        sm.to_stories_merged()
        assert sm.state == LinkerState.STORIES_MERGED

    def test_valid_transition_merged_to_final(self) -> None:
        """Test valid transition from STORIES_MERGED to STORIES_FINAL."""
        sm = LinkerStateMachine(
            run_id="test",
            initial_state=LinkerState.STORIES_MERGED,
        )
        assert sm.can_transition_to(LinkerState.STORIES_FINAL)
        sm.to_stories_final()
        assert sm.state == LinkerState.STORIES_FINAL

    def test_full_transition_sequence(self) -> None:
        """Test full transition sequence."""
        sm = LinkerStateMachine(run_id="test")

        sm.to_entity_tagged()
        assert sm.state == LinkerState.ENTITY_TAGGED

        sm.to_candidate_grouped()
        # After state transition, mypy incorrectly narrows state type
        assert sm.state == LinkerState.CANDIDATE_GROUPED  # type: ignore[comparison-overlap]

        sm.to_stories_merged()
        assert sm.state == LinkerState.STORIES_MERGED

        sm.to_stories_final()
        assert sm.state == LinkerState.STORIES_FINAL
        assert sm.is_terminal

    def test_invalid_transition_raises(self) -> None:
        """Test invalid transition raises error."""
        sm = LinkerStateMachine(run_id="test")
        with pytest.raises(LinkerStateTransitionError) as exc_info:
            sm.to_stories_final()  # Can't skip states

        assert exc_info.value.run_id == "test"
        assert exc_info.value.from_state == LinkerState.ITEMS_READY
        assert exc_info.value.to_state == LinkerState.STORIES_FINAL

    def test_cannot_transition_from_final(self) -> None:
        """Test no transitions from terminal state."""
        sm = LinkerStateMachine(
            run_id="test",
            initial_state=LinkerState.STORIES_FINAL,
        )
        assert not sm.can_transition_to(LinkerState.ITEMS_READY)
        assert not sm.can_transition_to(LinkerState.ENTITY_TAGGED)

    def test_cannot_skip_states(self) -> None:
        """Test that skipping states is not allowed."""
        sm = LinkerStateMachine(run_id="test")

        # Can't skip to CANDIDATE_GROUPED
        assert not sm.can_transition_to(LinkerState.CANDIDATE_GROUPED)

        # Can't skip to STORIES_MERGED
        assert not sm.can_transition_to(LinkerState.STORIES_MERGED)

        # Can't skip to STORIES_FINAL
        assert not sm.can_transition_to(LinkerState.STORIES_FINAL)


class TestLinkerStateTransitionError:
    """Tests for LinkerStateTransitionError exception."""

    def test_error_attributes(self) -> None:
        """Test error has correct attributes."""
        error = LinkerStateTransitionError(
            run_id="run-123",
            from_state=LinkerState.ITEMS_READY,
            to_state=LinkerState.STORIES_FINAL,
        )
        assert error.run_id == "run-123"
        assert error.from_state == LinkerState.ITEMS_READY
        assert error.to_state == LinkerState.STORIES_FINAL

    def test_error_message(self) -> None:
        """Test error message format."""
        error = LinkerStateTransitionError(
            run_id="run-123",
            from_state=LinkerState.ITEMS_READY,
            to_state=LinkerState.STORIES_FINAL,
        )
        assert "run-123" in str(error)
        assert "ITEMS_READY" in str(error)
        assert "STORIES_FINAL" in str(error)
