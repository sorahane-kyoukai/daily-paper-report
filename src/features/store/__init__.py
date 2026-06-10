"""SQLite state store for items, runs, and HTTP cache headers.

This module provides persistent storage for:
- Run lifecycle tracking (started, collecting, rendering, finished)
- Item storage with idempotent upserts and update detection
- HTTP cache headers for conditional requests
"""

from src.features.store.errors import (
    ConnectionError,
    ItemNotFoundError,
    MigrationError,
    RunNotFoundError,
    StateStoreError,
)
from src.features.store.hash import compute_content_hash
from src.features.store.metrics import (
    MetricsRecorder,
    NullMetricsRecorder,
    StoreMetrics,
)
from src.features.store.models import (
    DateConfidence,
    HttpCacheEntry,
    Item,
    ItemEventType,
    Run,
    UpsertResult,
)
from src.features.store.state_machine import RunState, RunStateError, RunStateMachine
from src.features.store.store import StateStore
from src.features.store.url import canonicalize_url


__all__ = [
    # Errors
    "ConnectionError",
    "ItemNotFoundError",
    "MigrationError",
    "RunNotFoundError",
    "StateStoreError",
    # Hash utilities
    "compute_content_hash",
    # Metrics
    "MetricsRecorder",
    "NullMetricsRecorder",
    "StoreMetrics",
    # Models
    "DateConfidence",
    "HttpCacheEntry",
    "Item",
    "ItemEventType",
    "Run",
    "UpsertResult",
    # State machine
    "RunState",
    "RunStateMachine",
    "RunStateError",
    # Store
    "StateStore",
    # URL utilities
    "canonicalize_url",
]
