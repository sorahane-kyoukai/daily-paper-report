"""Evidence capture module.

This module provides evidence capture functionality for
configuration snapshots, audit trails, and run reports.

Key components:
- EvidenceCapture: Main class for capturing evidence artifacts
- EvidenceWriter: Safe file writing with checksums and redaction
- Template functions: Render STATE.md and E2E_RUN_REPORT.md
- State machine: Enforce valid state transitions
- Redact: Secret detection and redaction
- Metrics: Track evidence writing metrics
"""

from src.features.evidence.capture import (
    ArtifactManifest,
    EvidenceCapture,
)
from src.features.evidence.metrics import EvidenceMetrics
from src.features.evidence.redact import (
    contains_secrets,
    get_secret_patterns,
    redact_content,
    scan_for_secrets,
)
from src.features.evidence.state_machine import (
    EvidenceState,
    EvidenceStateError,
    EvidenceStateMachine,
)
from src.features.evidence.template import (
    E2EReportTemplateData,
    StateTemplateData,
    render_e2e_report,
    render_state_md,
)
from src.features.evidence.writer import (
    ArtifactInfo,
    EvidenceWriteError,
    EvidenceWriter,
)


__all__ = [
    # capture.py
    "ArtifactManifest",
    "EvidenceCapture",
    # writer.py
    "ArtifactInfo",
    "EvidenceWriteError",
    "EvidenceWriter",
    # template.py
    "E2EReportTemplateData",
    "StateTemplateData",
    "render_e2e_report",
    "render_state_md",
    # metrics.py
    "EvidenceMetrics",
    # redact.py
    "contains_secrets",
    "get_secret_patterns",
    "redact_content",
    "scan_for_secrets",
    # state_machine.py
    "EvidenceState",
    "EvidenceStateError",
    "EvidenceStateMachine",
]
