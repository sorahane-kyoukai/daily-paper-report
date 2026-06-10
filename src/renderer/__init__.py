"""Static HTML renderer module."""

from src.renderer.io import AtomicWriter
from src.renderer.models import (
    DailyDigest,
    GeneratedFile,
    RenderConfig,
    RenderContext,
    RenderManifest,
    RenderResult,
    RunInfo,
    SourceStatus,
    SourceStatusCode,
)
from src.renderer.renderer import StaticRenderer, render_static
from src.renderer.state_machine import RenderState, RenderStateMachine


__all__ = [
    "AtomicWriter",
    "DailyDigest",
    "GeneratedFile",
    "RenderConfig",
    "RenderContext",
    "RenderManifest",
    "RenderResult",
    "RenderState",
    "RenderStateMachine",
    "RunInfo",
    "SourceStatus",
    "SourceStatusCode",
    "StaticRenderer",
    "render_static",
]
