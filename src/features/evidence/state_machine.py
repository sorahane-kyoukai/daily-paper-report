"""Evidence capture state machine implementation."""

from enum import Enum, auto
from typing import ClassVar

import structlog


logger = structlog.get_logger()


class EvidenceState(Enum):
    """Evidence capture states.

    State transitions:
        EVIDENCE_PENDING -> EVIDENCE_WRITING: Begin writing evidence files
        EVIDENCE_WRITING -> EVIDENCE_DONE: All evidence files written successfully
        EVIDENCE_WRITING -> EVIDENCE_FAILED: Evidence writing failed
        EVIDENCE_PENDING -> EVIDENCE_FAILED: Failed before writing started
    """

    EVIDENCE_PENDING = auto()
    EVIDENCE_WRITING = auto()
    EVIDENCE_DONE = auto()
    EVIDENCE_FAILED = auto()


class EvidenceStateError(Exception):
    """Raised when an invalid evidence state transition is attempted."""

    def __init__(self, from_state: EvidenceState, to_state: EvidenceState) -> None:
        """Initialize the error.

        Args:
            from_state: The current state.
            to_state: The attempted target state.
        """
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid evidence state transition: {from_state.name} -> {to_state.name}"
        )


class EvidenceStateMachine:
    """State machine for evidence capture.

    Enforces valid state transitions during evidence writing process.
    Logs invariant violations when invalid transitions are attempted.
    """

    VALID_TRANSITIONS: ClassVar[dict[EvidenceState, set[EvidenceState]]] = {
        EvidenceState.EVIDENCE_PENDING: {
            EvidenceState.EVIDENCE_WRITING,
            EvidenceState.EVIDENCE_FAILED,
        },
        EvidenceState.EVIDENCE_WRITING: {
            EvidenceState.EVIDENCE_DONE,
            EvidenceState.EVIDENCE_FAILED,
        },
        EvidenceState.EVIDENCE_DONE: set(),  # Terminal state
        EvidenceState.EVIDENCE_FAILED: set(),  # Terminal state
    }

    def __init__(self, run_id: str) -> None:
        """Initialize the state machine in EVIDENCE_PENDING state.

        Args:
            run_id: Unique run identifier for logging.
        """
        self._run_id = run_id
        self._state = EvidenceState.EVIDENCE_PENDING
        self._log = logger.bind(run_id=run_id, component="evidence")

    @property
    def state(self) -> EvidenceState:
        """Get the current state."""
        return self._state

    @property
    def run_id(self) -> str:
        """Get the run ID."""
        return self._run_id

    def can_transition(self, to_state: EvidenceState) -> bool:
        """Check if a transition to the given state is valid.

        Args:
            to_state: The target state.

        Returns:
            True if the transition is valid, False otherwise.
        """
        return to_state in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, to_state: EvidenceState) -> None:
        """Transition to a new state.

        Args:
            to_state: The target state.

        Raises:
            EvidenceStateError: If the transition is invalid.
        """
        if not self.can_transition(to_state):
            self._log.error(
                "invariant_violation",
                error_type="illegal_state_transition",
                from_state=self._state.name,
                to_state=to_state.name,
            )
            raise EvidenceStateError(self._state, to_state)

        old_state = self._state
        self._state = to_state
        self._log.info(
            "evidence_state_transition",
            from_state=old_state.name,
            to_state=to_state.name,
        )

    def is_terminal(self) -> bool:
        """Check if the current state is terminal (no more transitions allowed)."""
        return self._state in (
            EvidenceState.EVIDENCE_DONE,
            EvidenceState.EVIDENCE_FAILED,
        )

    def is_done(self) -> bool:
        """Check if evidence capture completed successfully."""
        return self._state == EvidenceState.EVIDENCE_DONE

    def is_failed(self) -> bool:
        """Check if evidence capture failed."""
        return self._state == EvidenceState.EVIDENCE_FAILED

    def is_pending(self) -> bool:
        """Check if evidence capture is pending."""
        return self._state == EvidenceState.EVIDENCE_PENDING

    def is_writing(self) -> bool:
        """Check if evidence capture is in writing phase."""
        return self._state == EvidenceState.EVIDENCE_WRITING
