"""E2E harness state machine for enforcing step order."""

from enum import Enum

import structlog


logger = structlog.get_logger()


class E2EState(Enum):
    """States for E2E harness execution.

    State transitions:
    PENDING -> CLEAR_DATA -> RUN_PIPELINE -> VALIDATE_DB -> VALIDATE_JSON
    -> VALIDATE_HTML -> ARCHIVE_EVIDENCE -> DONE
    Any state can transition to FAILED on error.
    """

    PENDING = "pending"
    CLEAR_DATA = "clear_data"
    RUN_PIPELINE = "run_pipeline"
    VALIDATE_DB = "validate_db"
    VALIDATE_JSON = "validate_json"
    VALIDATE_HTML = "validate_html"
    ARCHIVE_EVIDENCE = "archive_evidence"
    DONE = "done"
    FAILED = "failed"


# Valid state transitions (from_state -> [to_states])
_VALID_TRANSITIONS: dict[E2EState, list[E2EState]] = {
    E2EState.PENDING: [E2EState.CLEAR_DATA, E2EState.FAILED],
    E2EState.CLEAR_DATA: [E2EState.RUN_PIPELINE, E2EState.FAILED],
    E2EState.RUN_PIPELINE: [E2EState.VALIDATE_DB, E2EState.FAILED],
    E2EState.VALIDATE_DB: [E2EState.VALIDATE_JSON, E2EState.FAILED],
    E2EState.VALIDATE_JSON: [E2EState.VALIDATE_HTML, E2EState.FAILED],
    E2EState.VALIDATE_HTML: [E2EState.ARCHIVE_EVIDENCE, E2EState.FAILED],
    E2EState.ARCHIVE_EVIDENCE: [E2EState.DONE, E2EState.FAILED],
    E2EState.DONE: [],
    E2EState.FAILED: [],
}


class E2EStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: E2EState, to_state: E2EState) -> None:
        """Initialize the error.

        Args:
            from_state: Current state.
            to_state: Attempted target state.
        """
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid E2E state transition: {from_state.value} -> {to_state.value}"
        )


class E2EStateMachine:
    """State machine for E2E harness execution.

    Enforces the strict ordering of E2E steps:
    CLEAR_DATA -> RUN_PIPELINE -> VALIDATE_DB -> VALIDATE_JSON
    -> VALIDATE_HTML -> ARCHIVE_EVIDENCE -> DONE
    """

    def __init__(self, run_id: str) -> None:
        """Initialize the state machine.

        Args:
            run_id: Unique run identifier for logging.
        """
        self._state = E2EState.PENDING
        self._run_id = run_id
        self._log = logger.bind(
            component="e2e",
            run_id=run_id,
        )

    @property
    def state(self) -> E2EState:
        """Get the current state."""
        return self._state

    def is_pending(self) -> bool:
        """Check if in PENDING state."""
        return self._state == E2EState.PENDING

    def is_done(self) -> bool:
        """Check if in DONE state."""
        return self._state == E2EState.DONE

    def is_failed(self) -> bool:
        """Check if in FAILED state."""
        return self._state == E2EState.FAILED

    def is_terminal(self) -> bool:
        """Check if in a terminal state (DONE or FAILED)."""
        return self._state in (E2EState.DONE, E2EState.FAILED)

    def can_transition(self, to_state: E2EState) -> bool:
        """Check if a transition to the given state is valid.

        Args:
            to_state: Target state.

        Returns:
            True if transition is valid.
        """
        return to_state in _VALID_TRANSITIONS.get(self._state, [])

    def transition(self, to_state: E2EState) -> None:
        """Transition to a new state.

        Args:
            to_state: Target state.

        Raises:
            E2EStateTransitionError: If transition is invalid.
        """
        if not self.can_transition(to_state):
            raise E2EStateTransitionError(self._state, to_state)

        old_state = self._state
        self._state = to_state

        self._log.info(
            "e2e_state_transition",
            from_state=old_state.value,
            to_state=to_state.value,
        )

    def fail(self, reason: str) -> None:
        """Transition to FAILED state.

        Args:
            reason: Reason for failure.

        Raises:
            E2EStateTransitionError: If already in terminal state.
        """
        if self.is_terminal():
            self._log.warning(
                "e2e_already_terminal",
                current_state=self._state.value,
                reason=reason,
            )
            return

        old_state = self._state
        self._state = E2EState.FAILED

        self._log.warning(
            "e2e_state_failed",
            from_state=old_state.value,
            reason=reason,
        )

    def get_expected_next_state(self) -> E2EState | None:
        """Get the expected next state (excluding FAILED).

        Returns:
            Next state in sequence, or None if terminal.
        """
        valid = _VALID_TRANSITIONS.get(self._state, [])
        for state in valid:
            if state != E2EState.FAILED:
                return state
        return None
