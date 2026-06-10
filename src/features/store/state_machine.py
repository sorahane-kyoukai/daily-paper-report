"""Run lifecycle state machine implementation."""

from enum import Enum, auto
from typing import ClassVar

import structlog


logger = structlog.get_logger()


class RunState(Enum):
    """Run lifecycle states.

    State transitions:
        RUN_STARTED -> RUN_COLLECTING: Begin collecting items from sources
        RUN_COLLECTING -> RUN_RENDERING: All sources collected, begin rendering
        RUN_RENDERING -> RUN_FINISHED_SUCCESS: Rendering complete, run succeeded
        RUN_RENDERING -> RUN_FINISHED_FAILURE: Rendering failed
        RUN_STARTED/COLLECTING/RENDERING -> RUN_FINISHED_FAILURE: Failure at any stage
    """

    RUN_STARTED = auto()
    RUN_COLLECTING = auto()
    RUN_RENDERING = auto()
    RUN_FINISHED_SUCCESS = auto()
    RUN_FINISHED_FAILURE = auto()


class RunStateError(Exception):
    """Raised when an invalid run state transition is attempted."""

    def __init__(self, from_state: RunState, to_state: RunState) -> None:
        """Initialize the error.

        Args:
            from_state: The current state.
            to_state: The attempted target state.
        """
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid run state transition: {from_state.name} -> {to_state.name}"
        )


class RunStateMachine:
    """State machine for run lifecycle.

    Enforces valid state transitions during pipeline execution.
    Logs invariant violations when invalid transitions are attempted.
    """

    VALID_TRANSITIONS: ClassVar[dict[RunState, set[RunState]]] = {
        RunState.RUN_STARTED: {
            RunState.RUN_COLLECTING,
            RunState.RUN_FINISHED_FAILURE,
        },
        RunState.RUN_COLLECTING: {
            RunState.RUN_RENDERING,
            RunState.RUN_FINISHED_FAILURE,
        },
        RunState.RUN_RENDERING: {
            RunState.RUN_FINISHED_SUCCESS,
            RunState.RUN_FINISHED_FAILURE,
        },
        RunState.RUN_FINISHED_SUCCESS: set(),  # Terminal state
        RunState.RUN_FINISHED_FAILURE: set(),  # Terminal state
    }

    def __init__(self, run_id: str) -> None:
        """Initialize the state machine in RUN_STARTED state.

        Args:
            run_id: Unique run identifier for logging.
        """
        self._run_id = run_id
        self._state = RunState.RUN_STARTED
        self._log = logger.bind(run_id=run_id, component="store")

    @property
    def state(self) -> RunState:
        """Get the current state."""
        return self._state

    @property
    def run_id(self) -> str:
        """Get the run ID."""
        return self._run_id

    def can_transition(self, to_state: RunState) -> bool:
        """Check if a transition to the given state is valid.

        Args:
            to_state: The target state.

        Returns:
            True if the transition is valid, False otherwise.
        """
        return to_state in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, to_state: RunState) -> None:
        """Transition to a new state.

        Args:
            to_state: The target state.

        Raises:
            RunStateError: If the transition is invalid.
        """
        if not self.can_transition(to_state):
            self._log.error(
                "invariant_violation",
                error_type="illegal_state_transition",
                from_state=self._state.name,
                to_state=to_state.name,
            )
            raise RunStateError(self._state, to_state)

        old_state = self._state
        self._state = to_state
        self._log.info(
            "run_state_transition",
            from_state=old_state.name,
            to_state=to_state.name,
        )

    def is_terminal(self) -> bool:
        """Check if the current state is terminal (no more transitions allowed)."""
        return self._state in (
            RunState.RUN_FINISHED_SUCCESS,
            RunState.RUN_FINISHED_FAILURE,
        )

    def is_success(self) -> bool:
        """Check if run finished successfully."""
        return self._state == RunState.RUN_FINISHED_SUCCESS

    def is_failure(self) -> bool:
        """Check if run finished with failure."""
        return self._state == RunState.RUN_FINISHED_FAILURE

    def is_collecting(self) -> bool:
        """Check if run is in collecting phase."""
        return self._state == RunState.RUN_COLLECTING

    def is_rendering(self) -> bool:
        """Check if run is in rendering phase."""
        return self._state == RunState.RUN_RENDERING
