"""Unit tests for collector state machine."""

import pytest

from src.collectors.state_machine import (
    SourceState,
    SourceStateMachine,
    SourceStateTransitionError,
)


class TestSourceState:
    """Tests for SourceState enum."""

    def test_all_states_defined(self) -> None:
        """Verify all required states are defined."""
        assert SourceState.SOURCE_PENDING == "SOURCE_PENDING"
        assert SourceState.SOURCE_FETCHING == "SOURCE_FETCHING"
        assert SourceState.SOURCE_PARSING == "SOURCE_PARSING"
        assert SourceState.SOURCE_PARSING_LIST == "SOURCE_PARSING_LIST"
        assert SourceState.SOURCE_PARSING_ITEM_PAGES == "SOURCE_PARSING_ITEM_PAGES"
        assert SourceState.SOURCE_DONE == "SOURCE_DONE"
        assert SourceState.SOURCE_FAILED == "SOURCE_FAILED"

    def test_state_count(self) -> None:
        """Verify exactly 7 states exist."""
        assert len(SourceState) == 7


class TestSourceStateMachine:
    """Tests for SourceStateMachine."""

    def test_initial_state_is_pending(self) -> None:
        """State machine starts in SOURCE_PENDING."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        assert sm.state == SourceState.SOURCE_PENDING

    def test_custom_initial_state(self) -> None:
        """State machine can start in custom state."""
        sm = SourceStateMachine(
            source_id="test",
            run_id="run-1",
            initial_state=SourceState.SOURCE_FETCHING,
        )
        assert sm.state == SourceState.SOURCE_FETCHING

    def test_source_id_property(self) -> None:
        """Source ID is accessible."""
        sm = SourceStateMachine(source_id="my-source", run_id="run-1")
        assert sm.source_id == "my-source"

    def test_valid_transition_pending_to_fetching(self) -> None:
        """PENDING -> FETCHING is valid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        assert sm.state == SourceState.SOURCE_FETCHING

    def test_valid_transition_fetching_to_parsing(self) -> None:
        """FETCHING -> PARSING is valid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        sm.to_parsing()
        assert sm.state == SourceState.SOURCE_PARSING

    def test_valid_transition_parsing_to_done(self) -> None:
        """PARSING -> DONE is valid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        sm.to_parsing()
        sm.to_done()
        assert sm.state == SourceState.SOURCE_DONE

    def test_valid_transition_pending_to_failed(self) -> None:
        """PENDING -> FAILED is valid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_failed()
        assert sm.state == SourceState.SOURCE_FAILED

    def test_valid_transition_fetching_to_failed(self) -> None:
        """FETCHING -> FAILED is valid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        sm.to_failed()
        assert sm.state == SourceState.SOURCE_FAILED

    def test_valid_transition_parsing_to_failed(self) -> None:
        """PARSING -> FAILED is valid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        sm.to_parsing()
        sm.to_failed()
        assert sm.state == SourceState.SOURCE_FAILED

    def test_invalid_transition_pending_to_parsing(self) -> None:
        """PENDING -> PARSING is invalid (skips FETCHING)."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        with pytest.raises(SourceStateTransitionError) as exc_info:
            sm.to_parsing()
        assert exc_info.value.from_state == SourceState.SOURCE_PENDING
        assert exc_info.value.to_state == SourceState.SOURCE_PARSING

    def test_invalid_transition_pending_to_done(self) -> None:
        """PENDING -> DONE is invalid."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        with pytest.raises(SourceStateTransitionError):
            sm.to_done()

    def test_invalid_transition_from_done(self) -> None:
        """DONE is terminal - no transitions allowed."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        sm.to_parsing()
        sm.to_done()

        with pytest.raises(SourceStateTransitionError):
            sm.to_fetching()

    def test_invalid_transition_from_failed(self) -> None:
        """FAILED is terminal - no transitions allowed."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_failed()

        with pytest.raises(SourceStateTransitionError):
            sm.to_fetching()

    def test_is_terminal_done(self) -> None:
        """DONE is a terminal state."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_fetching()
        sm.to_parsing()
        sm.to_done()
        assert sm.is_terminal is True

    def test_is_terminal_failed(self) -> None:
        """FAILED is a terminal state."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        sm.to_failed()
        assert sm.is_terminal is True

    def test_is_not_terminal_pending(self) -> None:
        """PENDING is not terminal."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        assert sm.is_terminal is False

    def test_can_transition_to(self) -> None:
        """can_transition_to returns correct boolean."""
        sm = SourceStateMachine(source_id="test", run_id="run-1")
        assert sm.can_transition_to(SourceState.SOURCE_FETCHING) is True
        assert sm.can_transition_to(SourceState.SOURCE_FAILED) is True
        assert sm.can_transition_to(SourceState.SOURCE_PARSING) is False
        assert sm.can_transition_to(SourceState.SOURCE_DONE) is False

    def test_error_includes_source_id(self) -> None:
        """Transition error includes source ID."""
        sm = SourceStateMachine(source_id="my-source-123", run_id="run-1")
        with pytest.raises(SourceStateTransitionError) as exc_info:
            sm.to_parsing()
        assert exc_info.value.source_id == "my-source-123"
        assert "my-source-123" in str(exc_info.value)
