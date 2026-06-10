"""State machine for collector source processing."""

from enum import Enum

import structlog


logger = structlog.get_logger()


class SourceState(str, Enum):
    """State of a source during collection.

    States represent the lifecycle of a single source collection:
    - SOURCE_PENDING: Not yet started
    - SOURCE_FETCHING: HTTP request in progress
    - SOURCE_PARSING: Parsing response content (for rss_atom, arxiv, etc.)
    - SOURCE_PARSING_LIST: Parsing HTML list page (for html_list)
    - SOURCE_PARSING_ITEM_PAGES: Fetching item pages for date recovery (for html_list)
    - SOURCE_DONE: Successfully completed
    - SOURCE_FAILED: Failed with error
    """

    SOURCE_PENDING = "SOURCE_PENDING"
    SOURCE_FETCHING = "SOURCE_FETCHING"
    SOURCE_PARSING = "SOURCE_PARSING"
    SOURCE_PARSING_LIST = "SOURCE_PARSING_LIST"
    SOURCE_PARSING_ITEM_PAGES = "SOURCE_PARSING_ITEM_PAGES"
    SOURCE_DONE = "SOURCE_DONE"
    SOURCE_FAILED = "SOURCE_FAILED"


# Valid state transitions
_VALID_TRANSITIONS: dict[SourceState, set[SourceState]] = {
    SourceState.SOURCE_PENDING: {
        SourceState.SOURCE_FETCHING,
        SourceState.SOURCE_FAILED,
    },
    SourceState.SOURCE_FETCHING: {
        SourceState.SOURCE_PARSING,
        SourceState.SOURCE_PARSING_LIST,
        SourceState.SOURCE_FAILED,
    },
    SourceState.SOURCE_PARSING: {SourceState.SOURCE_DONE, SourceState.SOURCE_FAILED},
    # For html_list: list parsing can go to item pages or directly to done
    SourceState.SOURCE_PARSING_LIST: {
        SourceState.SOURCE_PARSING_ITEM_PAGES,
        SourceState.SOURCE_DONE,
        SourceState.SOURCE_FAILED,
    },
    # Item page parsing: can only complete or fail (not re-enter list parsing)
    SourceState.SOURCE_PARSING_ITEM_PAGES: {
        SourceState.SOURCE_DONE,
        SourceState.SOURCE_FAILED,
    },
    SourceState.SOURCE_DONE: set(),  # Terminal state
    SourceState.SOURCE_FAILED: set(),  # Terminal state
}


class SourceStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""

    def __init__(
        self,
        source_id: str,
        from_state: SourceState,
        to_state: SourceState,
    ) -> None:
        """Initialize the transition error.

        Args:
            source_id: Identifier of the source.
            from_state: Current state.
            to_state: Attempted target state.
        """
        self.source_id = source_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal state transition for source '{source_id}': "
            f"{from_state.value} -> {to_state.value}"
        )


class SourceStateMachine:
    """Manages state transitions for a source during collection.

    Enforces valid transitions and logs all state changes.
    """

    def __init__(
        self,
        source_id: str,
        run_id: str,
        initial_state: SourceState = SourceState.SOURCE_PENDING,
    ) -> None:
        """Initialize the state machine.

        Args:
            source_id: Identifier for the source.
            run_id: Identifier for the current run.
            initial_state: Starting state.
        """
        self._source_id = source_id
        self._run_id = run_id
        self._state = initial_state
        self._log = logger.bind(
            component="collector",
            run_id=run_id,
            source_id=source_id,
        )

    @property
    def source_id(self) -> str:
        """Get the source identifier."""
        return self._source_id

    @property
    def state(self) -> SourceState:
        """Get the current state."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._state in (SourceState.SOURCE_DONE, SourceState.SOURCE_FAILED)

    def can_transition_to(self, target: SourceState) -> bool:
        """Check if a transition to the target state is valid.

        Args:
            target: The target state.

        Returns:
            True if the transition is valid.
        """
        return target in _VALID_TRANSITIONS.get(self._state, set())

    def transition_to(self, target: SourceState) -> None:
        """Transition to a new state.

        Args:
            target: The target state.

        Raises:
            SourceStateTransitionError: If the transition is invalid.
        """
        if not self.can_transition_to(target):
            error = SourceStateTransitionError(
                source_id=self._source_id,
                from_state=self._state,
                to_state=target,
            )
            self._log.error(
                "illegal_state_transition",
                from_state=self._state.value,
                to_state=target.value,
            )
            raise error

        old_state = self._state
        self._state = target

        self._log.info(
            "state_transition",
            from_state=old_state.value,
            to_state=target.value,
        )

    def to_fetching(self) -> None:
        """Transition to SOURCE_FETCHING state."""
        self.transition_to(SourceState.SOURCE_FETCHING)

    def to_parsing(self) -> None:
        """Transition to SOURCE_PARSING state."""
        self.transition_to(SourceState.SOURCE_PARSING)

    def to_done(self) -> None:
        """Transition to SOURCE_DONE state."""
        self.transition_to(SourceState.SOURCE_DONE)

    def to_failed(self) -> None:
        """Transition to SOURCE_FAILED state."""
        self.transition_to(SourceState.SOURCE_FAILED)

    def to_parsing_list(self) -> None:
        """Transition to SOURCE_PARSING_LIST state (for html_list)."""
        self.transition_to(SourceState.SOURCE_PARSING_LIST)

    def to_parsing_item_pages(self) -> None:
        """Transition to SOURCE_PARSING_ITEM_PAGES state (for html_list).

        This can only be called after SOURCE_PARSING_LIST has succeeded.
        """
        self.transition_to(SourceState.SOURCE_PARSING_ITEM_PAGES)
