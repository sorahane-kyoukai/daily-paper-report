"""Configuration state machine implementation."""

from enum import Enum, auto
from typing import ClassVar


class ConfigState(Enum):
    """Configuration loading states.

    State transitions:
        UNLOADED -> LOADING: Start loading configuration files
        LOADING -> VALIDATED: All files loaded and validated successfully
        LOADING -> FAILED: Validation error occurred
        VALIDATED -> READY: Configuration finalized and ready for use
        Any -> FAILED: Error occurred at any stage
    """

    UNLOADED = auto()
    LOADING = auto()
    VALIDATED = auto()
    READY = auto()
    FAILED = auto()


class ConfigStateError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: ConfigState, to_state: ConfigState) -> None:
        """Initialize the error.

        Args:
            from_state: The current state.
            to_state: The attempted target state.
        """
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition: {from_state.name} -> {to_state.name}"
        )


class ConfigStateMachine:
    """State machine for configuration loading.

    Enforces valid state transitions during configuration loading process.
    """

    VALID_TRANSITIONS: ClassVar[dict[ConfigState, set[ConfigState]]] = {
        ConfigState.UNLOADED: {ConfigState.LOADING, ConfigState.FAILED},
        ConfigState.LOADING: {ConfigState.VALIDATED, ConfigState.FAILED},
        ConfigState.VALIDATED: {ConfigState.READY, ConfigState.FAILED},
        ConfigState.READY: {ConfigState.FAILED},
        ConfigState.FAILED: set(),  # Terminal state
    }

    def __init__(self) -> None:
        """Initialize the state machine in UNLOADED state."""
        self._state = ConfigState.UNLOADED

    @property
    def state(self) -> ConfigState:
        """Get the current state."""
        return self._state

    def can_transition(self, to_state: ConfigState) -> bool:
        """Check if a transition to the given state is valid.

        Args:
            to_state: The target state.

        Returns:
            True if the transition is valid, False otherwise.
        """
        return to_state in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, to_state: ConfigState) -> None:
        """Transition to a new state.

        Args:
            to_state: The target state.

        Raises:
            ConfigStateError: If the transition is invalid.
        """
        if not self.can_transition(to_state):
            raise ConfigStateError(self._state, to_state)
        self._state = to_state

    def is_terminal(self) -> bool:
        """Check if the current state is terminal (no more transitions allowed)."""
        return self._state == ConfigState.FAILED

    def is_ready(self) -> bool:
        """Check if configuration is ready for use."""
        return self._state == ConfigState.READY

    def is_failed(self) -> bool:
        """Check if configuration loading has failed."""
        return self._state == ConfigState.FAILED
