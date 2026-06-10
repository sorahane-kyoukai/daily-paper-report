"""Shared, deterministic timestamps for tests."""

from datetime import UTC, datetime


# Fixed timestamp to keep time-window filters deterministic across environments.
# Choose a value that keeps all fixture dates within lookback windows.
FIXED_NOW = datetime(2017, 6, 13, 0, 0, 0, tzinfo=UTC)
