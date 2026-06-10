"""Unit tests for renderer state machine."""

import pytest

from src.renderer.state_machine import (
    RenderState,
    RenderStateError,
    RenderStateMachine,
)


class TestRenderStateMachine:
    """Tests for RenderStateMachine."""

    def test_initial_state_is_pending(self) -> None:
        """State machine starts in RENDER_PENDING."""
        sm = RenderStateMachine("test-run")
        assert sm.state == RenderState.RENDER_PENDING

    def test_run_id_is_set(self) -> None:
        """Run ID is accessible."""
        sm = RenderStateMachine("my-run-id")
        assert sm.run_id == "my-run-id"

    def test_valid_transition_pending_to_json(self) -> None:
        """Can transition from PENDING to RENDERING_JSON."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        assert sm.state == RenderState.RENDERING_JSON

    def test_valid_transition_json_to_html(self) -> None:
        """Can transition from RENDERING_JSON to RENDERING_HTML."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        sm.to_rendering_html()
        assert sm.state == RenderState.RENDERING_HTML

    def test_valid_transition_html_to_done(self) -> None:
        """Can transition from RENDERING_HTML to RENDER_DONE."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        sm.to_rendering_html()
        sm.to_done()
        assert sm.state == RenderState.RENDER_DONE
        assert sm.is_done()
        assert sm.is_terminal()

    def test_valid_transition_to_failed_from_pending(self) -> None:
        """Can transition from PENDING to FAILED."""
        sm = RenderStateMachine("test")
        sm.to_failed()
        assert sm.state == RenderState.RENDER_FAILED
        assert sm.is_failed()
        assert sm.is_terminal()

    def test_valid_transition_to_failed_from_json(self) -> None:
        """Can transition from RENDERING_JSON to FAILED."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        sm.to_failed()
        assert sm.state == RenderState.RENDER_FAILED

    def test_valid_transition_to_failed_from_html(self) -> None:
        """Can transition from RENDERING_HTML to FAILED."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        sm.to_rendering_html()
        sm.to_failed()
        assert sm.state == RenderState.RENDER_FAILED

    def test_invalid_transition_pending_to_html(self) -> None:
        """Cannot skip from PENDING directly to RENDERING_HTML."""
        sm = RenderStateMachine("test")
        with pytest.raises(RenderStateError) as exc_info:
            sm.to_rendering_html()
        assert exc_info.value.from_state == RenderState.RENDER_PENDING
        assert exc_info.value.to_state == RenderState.RENDERING_HTML

    def test_invalid_transition_pending_to_done(self) -> None:
        """Cannot go from PENDING directly to DONE."""
        sm = RenderStateMachine("test")
        with pytest.raises(RenderStateError):
            sm.to_done()

    def test_invalid_transition_json_to_done(self) -> None:
        """Cannot skip from RENDERING_JSON to DONE."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        with pytest.raises(RenderStateError):
            sm.to_done()

    def test_terminal_state_done_no_transitions(self) -> None:
        """Cannot transition from DONE."""
        sm = RenderStateMachine("test")
        sm.to_rendering_json()
        sm.to_rendering_html()
        sm.to_done()
        with pytest.raises(RenderStateError):
            sm.to_failed()

    def test_terminal_state_failed_no_transitions(self) -> None:
        """Cannot transition from FAILED."""
        sm = RenderStateMachine("test")
        sm.to_failed()
        with pytest.raises(RenderStateError):
            sm.to_rendering_json()

    def test_can_transition_check(self) -> None:
        """can_transition returns correct boolean."""
        sm = RenderStateMachine("test")
        assert sm.can_transition(RenderState.RENDERING_JSON)
        assert not sm.can_transition(RenderState.RENDERING_HTML)
        assert not sm.can_transition(RenderState.RENDER_DONE)
        assert sm.can_transition(RenderState.RENDER_FAILED)

    def test_is_terminal_false_for_pending(self) -> None:
        """PENDING is not terminal."""
        sm = RenderStateMachine("test")
        assert not sm.is_terminal()

    def test_is_done_and_is_failed(self) -> None:
        """is_done and is_failed work correctly."""
        sm = RenderStateMachine("test")
        assert not sm.is_done()
        assert not sm.is_failed()

        sm.to_rendering_json()
        sm.to_rendering_html()
        sm.to_done()
        assert sm.is_done()
        assert not sm.is_failed()

    def test_error_message_format(self) -> None:
        """RenderStateError has correct message."""
        sm = RenderStateMachine("test")
        with pytest.raises(RenderStateError) as exc_info:
            sm.to_done()
        assert "RENDER_PENDING" in str(exc_info.value)
        assert "RENDER_DONE" in str(exc_info.value)
