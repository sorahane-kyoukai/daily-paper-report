"""Source status classification and degradation reporting.

This module provides:
- ReasonCode enum for machine-readable status reason codes
- SourceCategory enum for grouping sources by category
- StatusComputer for computing per-source status from collector results
- StatusSummary for pre-computed summary statistics
- Error mappers for extensible error-to-reason-code mapping
- Metrics for status tracking
"""

from src.features.status.computer import StatusComputer
from src.features.status.error_mapper import (
    map_fetch_error_to_reason_code,
    map_http_status_to_reason_code,
    map_parse_error_to_reason_code,
)
from src.features.status.models import ReasonCode, SourceCategory, StatusSummary


__all__ = [
    "ReasonCode",
    "SourceCategory",
    "StatusComputer",
    "StatusSummary",
    "map_fetch_error_to_reason_code",
    "map_http_status_to_reason_code",
    "map_parse_error_to_reason_code",
]
