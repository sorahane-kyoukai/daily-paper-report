"""Render lifecycle state machine implementation."""

from enum import Enum, auto
from typing import ClassVar

import structlog


logger = structlog.get_logger()


class RenderState(Enum):
    """Render lifecycle states.

    State transitions:
        RENDER_PENDING -> RENDERING_JSON: Begin JSON rendering
        RENDERING_JSON -> RENDERING_HTML: JSON complete, begin HTML rendering
        RENDERING_HTML -> RENDER_DONE: All rendering complete
        RENDERING_JSON/RENDERING_HTML -> RENDER_FAILED: Rendering failed
    """

    RENDER_PENDING = auto()
    RENDERING_JSON = auto()
    RENDERING_HTML = auto()
    RENDER_DONE = auto()
    RENDER_FAILED = auto()


class RenderStateError(Exception):
    """Raised when an invalid render state transition is attempted."""

    def __init__(self, from_state: RenderState, to_state: RenderState) -> None:
        """Initialize the error.

        Args:
            from_state: The current state.
            to_state: The attempted target state.
        """
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid render state transition: {from_state.name} -> {to_state.name}"
        )


class RenderStateMachine:
    """State machine for render lifecycle.

    Enforces valid state transitions during rendering.
    Logs invariant violations when invalid transitions are attempted.
    """

    VALID_TRANSITIONS: ClassVar[dict[RenderState, set[RenderState]]] = {
        RenderState.RENDER_PENDING: {
            RenderState.RENDERING_JSON,
            RenderState.RENDER_FAILED,
        },
        RenderState.RENDERING_JSON: {
            RenderState.RENDERING_HTML,
            RenderState.RENDER_FAILED,
        },
        RenderState.RENDERING_HTML: {
            RenderState.RENDER_DONE,
            RenderState.RENDER_FAILED,
        },
        RenderState.RENDER_DONE: set(),  # Terminal state
        RenderState.RENDER_FAILED: set(),  # Terminal state
    }

    def __init__(self, run_id: str) -> None:
        """Initialize the state machine in RENDER_PENDING state.

        Args:
            run_id: Unique run identifier for logging.
        """
        self._run_id = run_id
        self._state = RenderState.RENDER_PENDING
        self._log = logger.bind(run_id=run_id, component="renderer")

    @property
    def state(self) -> RenderState:
        """Get the current state."""
        return self._state

    @property
    def run_id(self) -> str:
        """Get the run ID."""
        return self._run_id

    def can_transition(self, to_state: RenderState) -> bool:
        """Check if a transition to the given state is valid.

        Args:
            to_state: The target state.

        Returns:
            True if the transition is valid, False otherwise.
        """
        return to_state in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, to_state: RenderState) -> None:
        """Transition to a new state.

        Args:
            to_state: The target state.

        Raises:
            RenderStateError: If the transition is invalid.
        """
        if not self.can_transition(to_state):
            self._log.error(
                "invariant_violation",
                error_type="illegal_state_transition",
                from_state=self._state.name,
                to_state=to_state.name,
            )
            raise RenderStateError(self._state, to_state)

        old_state = self._state
        self._state = to_state
        self._log.info(
            "render_state_transition",
            from_state=old_state.name,
            to_state=to_state.name,
        )

    def to_rendering_json(self) -> None:
        """Transition to RENDERING_JSON state."""
        self.transition(RenderState.RENDERING_JSON)

    def to_rendering_html(self) -> None:
        """Transition to RENDERING_HTML state."""
        self.transition(RenderState.RENDERING_HTML)

    def to_done(self) -> None:
        """Transition to RENDER_DONE state."""
        self.transition(RenderState.RENDER_DONE)

    def to_failed(self) -> None:
        """Transition to RENDER_FAILED state."""
        self.transition(RenderState.RENDER_FAILED)

    def is_terminal(self) -> bool:
        """Check if the current state is terminal."""
        return self._state in (RenderState.RENDER_DONE, RenderState.RENDER_FAILED)

    def is_done(self) -> bool:
        """Check if rendering completed successfully."""
        return self._state == RenderState.RENDER_DONE

    def is_failed(self) -> bool:
        """Check if rendering failed."""
        return self._state == RenderState.RENDER_FAILED
