"""Unit tests for run state machine."""

import pytest

from src.features.store.state_machine import RunState, RunStateError, RunStateMachine


class TestRunState:
    """Tests for RunState enum."""

    def test_all_states_exist(self) -> None:
        """Test all expected states exist."""
        assert RunState.RUN_STARTED is not None
        assert RunState.RUN_COLLECTING is not None
        assert RunState.RUN_RENDERING is not None
        assert RunState.RUN_FINISHED_SUCCESS is not None
        assert RunState.RUN_FINISHED_FAILURE is not None


class TestRunStateMachine:
    """Tests for RunStateMachine."""

    def test_initial_state(self) -> None:
        """Test machine starts in RUN_STARTED state."""
        machine = RunStateMachine(run_id="test-run")
        assert machine.state == RunState.RUN_STARTED
        assert machine.run_id == "test-run"

    def test_valid_transition_started_to_collecting(self) -> None:
        """Test valid transition from STARTED to COLLECTING."""
        machine = RunStateMachine(run_id="test")
        assert machine.can_transition(RunState.RUN_COLLECTING)
        machine.transition(RunState.RUN_COLLECTING)
        assert machine.state == RunState.RUN_COLLECTING
        assert machine.is_collecting()

    def test_valid_transition_collecting_to_rendering(self) -> None:
        """Test valid transition from COLLECTING to RENDERING."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_COLLECTING)
        assert machine.can_transition(RunState.RUN_RENDERING)
        machine.transition(RunState.RUN_RENDERING)
        assert machine.state == RunState.RUN_RENDERING
        assert machine.is_rendering()

    def test_valid_transition_rendering_to_success(self) -> None:
        """Test valid transition from RENDERING to SUCCESS."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_COLLECTING)
        machine.transition(RunState.RUN_RENDERING)
        assert machine.can_transition(RunState.RUN_FINISHED_SUCCESS)
        machine.transition(RunState.RUN_FINISHED_SUCCESS)
        assert machine.state == RunState.RUN_FINISHED_SUCCESS
        assert machine.is_success()
        assert machine.is_terminal()

    def test_valid_transition_rendering_to_failure(self) -> None:
        """Test valid transition from RENDERING to FAILURE."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_COLLECTING)
        machine.transition(RunState.RUN_RENDERING)
        assert machine.can_transition(RunState.RUN_FINISHED_FAILURE)
        machine.transition(RunState.RUN_FINISHED_FAILURE)
        assert machine.state == RunState.RUN_FINISHED_FAILURE
        assert machine.is_failure()
        assert machine.is_terminal()

    def test_failure_from_started(self) -> None:
        """Test can transition to FAILURE from STARTED."""
        machine = RunStateMachine(run_id="test")
        assert machine.can_transition(RunState.RUN_FINISHED_FAILURE)
        machine.transition(RunState.RUN_FINISHED_FAILURE)
        assert machine.is_failure()

    def test_failure_from_collecting(self) -> None:
        """Test can transition to FAILURE from COLLECTING."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_COLLECTING)
        assert machine.can_transition(RunState.RUN_FINISHED_FAILURE)
        machine.transition(RunState.RUN_FINISHED_FAILURE)
        assert machine.is_failure()

    def test_invalid_transition_started_to_rendering(self) -> None:
        """Test invalid transition from STARTED to RENDERING."""
        machine = RunStateMachine(run_id="test")
        assert not machine.can_transition(RunState.RUN_RENDERING)
        with pytest.raises(RunStateError) as exc_info:
            machine.transition(RunState.RUN_RENDERING)

        assert exc_info.value.from_state == RunState.RUN_STARTED
        assert exc_info.value.to_state == RunState.RUN_RENDERING

    def test_invalid_transition_started_to_success(self) -> None:
        """Test invalid transition from STARTED to SUCCESS."""
        machine = RunStateMachine(run_id="test")
        assert not machine.can_transition(RunState.RUN_FINISHED_SUCCESS)
        with pytest.raises(RunStateError):
            machine.transition(RunState.RUN_FINISHED_SUCCESS)

    def test_invalid_transition_collecting_to_success(self) -> None:
        """Test invalid transition from COLLECTING to SUCCESS."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_COLLECTING)
        assert not machine.can_transition(RunState.RUN_FINISHED_SUCCESS)
        with pytest.raises(RunStateError):
            machine.transition(RunState.RUN_FINISHED_SUCCESS)

    def test_no_transition_from_success(self) -> None:
        """Test no transitions allowed from SUCCESS (terminal)."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_COLLECTING)
        machine.transition(RunState.RUN_RENDERING)
        machine.transition(RunState.RUN_FINISHED_SUCCESS)

        assert machine.is_terminal()
        for state in RunState:
            assert not machine.can_transition(state)

    def test_no_transition_from_failure(self) -> None:
        """Test no transitions allowed from FAILURE (terminal)."""
        machine = RunStateMachine(run_id="test")
        machine.transition(RunState.RUN_FINISHED_FAILURE)

        assert machine.is_terminal()
        for state in RunState:
            assert not machine.can_transition(state)

    def test_error_message_format(self) -> None:
        """Test RunStateError message format."""
        error = RunStateError(RunState.RUN_STARTED, RunState.RUN_RENDERING)
        assert "RUN_STARTED" in str(error)
        assert "RUN_RENDERING" in str(error)

    def test_full_successful_lifecycle(self) -> None:
        """Test complete successful run lifecycle."""
        machine = RunStateMachine(run_id="test")

        # Start -> Collecting
        assert machine.state == RunState.RUN_STARTED
        assert not machine.is_terminal()

        machine.transition(RunState.RUN_COLLECTING)
        assert machine.is_collecting()

        # Collecting -> Rendering
        machine.transition(RunState.RUN_RENDERING)
        assert machine.is_rendering()

        # Rendering -> Success
        machine.transition(RunState.RUN_FINISHED_SUCCESS)
        assert machine.is_success()
        assert machine.is_terminal()
        assert not machine.is_failure()

    def test_full_failed_lifecycle(self) -> None:
        """Test complete failed run lifecycle."""
        machine = RunStateMachine(run_id="test")

        machine.transition(RunState.RUN_COLLECTING)
        machine.transition(RunState.RUN_RENDERING)
        machine.transition(RunState.RUN_FINISHED_FAILURE)

        assert machine.is_failure()
        assert machine.is_terminal()
        assert not machine.is_success()
