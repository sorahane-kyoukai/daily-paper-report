"""State machine for Story linker processing."""

from enum import Enum

import structlog


logger = structlog.get_logger()


class LinkerState(str, Enum):
    """State of the linker during processing.

    States represent the lifecycle of Story linking:
    - ITEMS_READY: Input items are ready for processing
    - ENTITY_TAGGED: Items have been tagged with matching entities
    - CANDIDATE_GROUPED: Items have been grouped into candidate clusters
    - STORIES_MERGED: Candidates have been merged into Stories
    - STORIES_FINAL: Stories are finalized and ready for output
    """

    ITEMS_READY = "ITEMS_READY"
    ENTITY_TAGGED = "ENTITY_TAGGED"
    CANDIDATE_GROUPED = "CANDIDATE_GROUPED"
    STORIES_MERGED = "STORIES_MERGED"
    STORIES_FINAL = "STORIES_FINAL"


# Valid state transitions
_VALID_TRANSITIONS: dict[LinkerState, set[LinkerState]] = {
    LinkerState.ITEMS_READY: {LinkerState.ENTITY_TAGGED},
    LinkerState.ENTITY_TAGGED: {LinkerState.CANDIDATE_GROUPED},
    LinkerState.CANDIDATE_GROUPED: {LinkerState.STORIES_MERGED},
    LinkerState.STORIES_MERGED: {LinkerState.STORIES_FINAL},
    LinkerState.STORIES_FINAL: set(),  # Terminal state
}


class LinkerStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""

    def __init__(
        self,
        run_id: str,
        from_state: LinkerState,
        to_state: LinkerState,
    ) -> None:
        """Initialize the transition error.

        Args:
            run_id: Identifier of the run.
            from_state: Current state.
            to_state: Attempted target state.
        """
        self.run_id = run_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal linker state transition for run '{run_id}': "
            f"{from_state.value} -> {to_state.value}"
        )


class LinkerStateMachine:
    """Manages state transitions for Story linking.

    Enforces valid transitions and logs all state changes.
    """

    def __init__(
        self,
        run_id: str,
        initial_state: LinkerState = LinkerState.ITEMS_READY,
    ) -> None:
        """Initialize the state machine.

        Args:
            run_id: Identifier for the current run.
            initial_state: Starting state.
        """
        self._run_id = run_id
        self._state = initial_state
        self._log = logger.bind(
            component="linker",
            run_id=run_id,
        )

    @property
    def run_id(self) -> str:
        """Get the run identifier."""
        return self._run_id

    @property
    def state(self) -> LinkerState:
        """Get the current state."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._state == LinkerState.STORIES_FINAL

    def can_transition_to(self, target: LinkerState) -> bool:
        """Check if a transition to the target state is valid.

        Args:
            target: The target state.

        Returns:
            True if the transition is valid.
        """
        return target in _VALID_TRANSITIONS.get(self._state, set())

    def transition_to(self, target: LinkerState) -> None:
        """Transition to a new state.

        Args:
            target: The target state.

        Raises:
            LinkerStateTransitionError: If the transition is invalid.
        """
        if not self.can_transition_to(target):
            error = LinkerStateTransitionError(
                run_id=self._run_id,
                from_state=self._state,
                to_state=target,
            )
            self._log.error(
                "illegal_linker_state_transition",
                from_state=self._state.value,
                to_state=target.value,
            )
            raise error

        old_state = self._state
        self._state = target

        self._log.info(
            "linker_state_transition",
            from_state=old_state.value,
            to_state=target.value,
        )

    def to_entity_tagged(self) -> None:
        """Transition to ENTITY_TAGGED state."""
        self.transition_to(LinkerState.ENTITY_TAGGED)

    def to_candidate_grouped(self) -> None:
        """Transition to CANDIDATE_GROUPED state."""
        self.transition_to(LinkerState.CANDIDATE_GROUPED)

    def to_stories_merged(self) -> None:
        """Transition to STORIES_MERGED state."""
        self.transition_to(LinkerState.STORIES_MERGED)

    def to_stories_final(self) -> None:
        """Transition to STORIES_FINAL state."""
        self.transition_to(LinkerState.STORIES_FINAL)
