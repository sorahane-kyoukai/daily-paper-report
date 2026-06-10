"""Unit tests for configuration state machine."""

import pytest

from src.features.config.state_machine import (
    ConfigState,
    ConfigStateError,
    ConfigStateMachine,
)


class TestConfigState:
    """Tests for ConfigState enum."""

    @pytest.mark.unit
    def test_all_states_defined(self) -> None:
        """Test that all expected states are defined."""
        expected_states = {"UNLOADED", "LOADING", "VALIDATED", "READY", "FAILED"}
        actual_states = {state.name for state in ConfigState}
        assert actual_states == expected_states


class TestConfigStateMachine:
    """Tests for ConfigStateMachine."""

    @pytest.mark.unit
    def test_initial_state(self) -> None:
        """Test that initial state is UNLOADED."""
        machine = ConfigStateMachine()
        assert machine.state == ConfigState.UNLOADED

    @pytest.mark.unit
    def test_valid_transition_unloaded_to_loading(self) -> None:
        """Test valid transition from UNLOADED to LOADING."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.LOADING)
        assert machine.state == ConfigState.LOADING

    @pytest.mark.unit
    def test_valid_transition_loading_to_validated(self) -> None:
        """Test valid transition from LOADING to VALIDATED."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.LOADING)
        machine.transition(ConfigState.VALIDATED)
        assert machine.state == ConfigState.VALIDATED

    @pytest.mark.unit
    def test_valid_transition_validated_to_ready(self) -> None:
        """Test valid transition from VALIDATED to READY."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.LOADING)
        machine.transition(ConfigState.VALIDATED)
        machine.transition(ConfigState.READY)
        assert machine.state == ConfigState.READY

    @pytest.mark.unit
    def test_valid_transition_to_failed_from_any(self) -> None:
        """Test that any state can transition to FAILED."""
        for start_state in [
            ConfigState.UNLOADED,
            ConfigState.LOADING,
            ConfigState.VALIDATED,
            ConfigState.READY,
        ]:
            machine = ConfigStateMachine()
            # Get to start state
            if start_state == ConfigState.LOADING:
                machine.transition(ConfigState.LOADING)
            elif start_state == ConfigState.VALIDATED:
                machine.transition(ConfigState.LOADING)
                machine.transition(ConfigState.VALIDATED)
            elif start_state == ConfigState.READY:
                machine.transition(ConfigState.LOADING)
                machine.transition(ConfigState.VALIDATED)
                machine.transition(ConfigState.READY)

            assert machine.state == start_state
            machine.transition(ConfigState.FAILED)
            assert machine.state == ConfigState.FAILED

    @pytest.mark.unit
    def test_invalid_transition_unloaded_to_validated(self) -> None:
        """Test invalid transition from UNLOADED directly to VALIDATED."""
        machine = ConfigStateMachine()
        with pytest.raises(ConfigStateError) as exc_info:
            machine.transition(ConfigState.VALIDATED)
        assert exc_info.value.from_state == ConfigState.UNLOADED
        assert exc_info.value.to_state == ConfigState.VALIDATED

    @pytest.mark.unit
    def test_invalid_transition_loading_to_ready(self) -> None:
        """Test invalid transition from LOADING directly to READY."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.LOADING)
        with pytest.raises(ConfigStateError):
            machine.transition(ConfigState.READY)

    @pytest.mark.unit
    def test_invalid_transition_from_failed(self) -> None:
        """Test that no transitions are allowed from FAILED."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.FAILED)
        with pytest.raises(ConfigStateError):
            machine.transition(ConfigState.UNLOADED)
        with pytest.raises(ConfigStateError):
            machine.transition(ConfigState.LOADING)

    @pytest.mark.unit
    def test_can_transition_true(self) -> None:
        """Test can_transition returns True for valid transitions."""
        machine = ConfigStateMachine()
        assert machine.can_transition(ConfigState.LOADING) is True
        assert machine.can_transition(ConfigState.FAILED) is True

    @pytest.mark.unit
    def test_can_transition_false(self) -> None:
        """Test can_transition returns False for invalid transitions."""
        machine = ConfigStateMachine()
        assert machine.can_transition(ConfigState.VALIDATED) is False
        assert machine.can_transition(ConfigState.READY) is False

    @pytest.mark.unit
    def test_is_terminal_false(self) -> None:
        """Test is_terminal returns False for non-terminal states."""
        machine = ConfigStateMachine()
        assert machine.is_terminal() is False
        machine.transition(ConfigState.LOADING)
        assert machine.is_terminal() is False

    @pytest.mark.unit
    def test_is_terminal_true(self) -> None:
        """Test is_terminal returns True for FAILED state."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.FAILED)
        assert machine.is_terminal() is True

    @pytest.mark.unit
    def test_is_ready_false(self) -> None:
        """Test is_ready returns False before READY state."""
        machine = ConfigStateMachine()
        assert machine.is_ready() is False
        machine.transition(ConfigState.LOADING)
        assert machine.is_ready() is False
        machine.transition(ConfigState.VALIDATED)
        assert machine.is_ready() is False

    @pytest.mark.unit
    def test_is_ready_true(self) -> None:
        """Test is_ready returns True in READY state."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.LOADING)
        machine.transition(ConfigState.VALIDATED)
        machine.transition(ConfigState.READY)
        assert machine.is_ready() is True

    @pytest.mark.unit
    def test_is_failed_true(self) -> None:
        """Test is_failed returns True in FAILED state."""
        machine = ConfigStateMachine()
        machine.transition(ConfigState.FAILED)
        assert machine.is_failed() is True

    @pytest.mark.unit
    def test_is_failed_false(self) -> None:
        """Test is_failed returns False in other states."""
        machine = ConfigStateMachine()
        assert machine.is_failed() is False
        machine.transition(ConfigState.LOADING)
        assert machine.is_failed() is False


class TestConfigStateError:
    """Tests for ConfigStateError."""

    @pytest.mark.unit
    def test_error_message(self) -> None:
        """Test error message format."""
        error = ConfigStateError(ConfigState.UNLOADED, ConfigState.READY)
        assert "UNLOADED" in str(error)
        assert "READY" in str(error)
        assert "Invalid state transition" in str(error)

    @pytest.mark.unit
    def test_error_attributes(self) -> None:
        """Test error has correct attributes."""
        error = ConfigStateError(ConfigState.LOADING, ConfigState.UNLOADED)
        assert error.from_state == ConfigState.LOADING
        assert error.to_state == ConfigState.UNLOADED
