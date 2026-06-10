"""Base collector interface and utilities."""

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

import structlog

from src.collectors.errors import ErrorRecord
from src.collectors.state_machine import SourceState
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.models import Item
from src.features.store.url import canonicalize_url


# Maximum size for raw_json in bytes
RAW_JSON_MAX_SIZE = 100 * 1024  # 100KB

# Truncation threshold for individual fields
FIELD_TRUNCATION_THRESHOLD = 100


@dataclass(frozen=True)
class CollectorResult:
    """Result of a collector execution.

    Contains collected items, any parse warnings, and final state.
    """

    items: list[Item]
    parse_warnings: list[str] = field(default_factory=list)
    error: ErrorRecord | None = None
    state: SourceState = SourceState.SOURCE_DONE

    @property
    def success(self) -> bool:
        """Check if collection succeeded."""
        return self.state == SourceState.SOURCE_DONE

    @property
    def items_count(self) -> int:
        """Get number of items collected."""
        return len(self.items)


@runtime_checkable
class Collector(Protocol):
    """Protocol for source collectors.

    Collectors are responsible for:
    1. Fetching content from a source
    2. Parsing content into normalized Items
    3. Handling errors appropriately
    """

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect items from a source.

        Args:
            source_config: Configuration for the source.
            http_client: HTTP client for fetching.
            now: Current timestamp for consistency.
            lookback_hours: Number of hours to look back for items.

        Returns:
            CollectorResult with items and status.
        """
        ...


class BaseCollector(ABC):
    """Abstract base class for collectors.

    Provides common functionality for all collector implementations.
    """

    def __init__(self, strip_params: list[str] | None = None) -> None:
        """Initialize the base collector.

        Args:
            strip_params: URL parameters to strip for canonicalization.
        """
        self._strip_params = strip_params

    @abstractmethod
    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect items from a source.

        Args:
            source_config: Configuration for the source.
            http_client: HTTP client for fetching.
            now: Current timestamp for consistency.
            lookback_hours: Number of hours to look back for items.
            max_items_override: Optional runtime override for source max_items. If
                provided, overrides source_config.max_items. A value of 0 disables
                source-level capping while still allowing a safe request fetch cap.

        Returns:
            CollectorResult with items and status.
        """

    @staticmethod
    def resolve_max_items(
        source_max_items: int,
        max_items_override: int | None,
    ) -> int:
        """Resolve effective max_items for this run.

        Args:
            source_max_items: Configured per-source max_items.
            max_items_override: Optional runtime override.

        Returns:
            Effective max_items (may be 0 for unlimited).
        """
        if max_items_override is None:
            return source_max_items
        return max_items_override

    @staticmethod
    def resolve_fetch_limit(
        max_items: int,
        fallback_limit: int,
        api_cap: int | None = None,
    ) -> int:
        """Resolve safe request-time fetch limit.

        A runtime/config value of 0 means no collection cap, but upstream APIs
        still require a finite request limit. This helper converts <=0 values to
        a sensible fallback and optionally applies provider API caps.

        Args:
            max_items: Resolved max_items from config/override.
            fallback_limit: Fallback fetch limit when max_items <= 0.
            api_cap: Optional API maximum cap.

        Returns:
            Effective limit for fetch/query parameters.
        """
        if max_items <= 0:
            max_items = fallback_limit

        if api_cap is not None:
            return min(max_items, api_cap)

        return max_items

    def canonicalize_url(self, url: str, base_url: str | None = None) -> str:
        """Canonicalize a URL.

        Args:
            url: The URL to canonicalize.
            base_url: Optional base URL for resolving relative URLs.

        Returns:
            Canonicalized URL.
        """
        # Resolve relative URLs
        if base_url and not url.startswith(("http://", "https://")):
            from urllib.parse import urljoin

            url = urljoin(base_url, url)

        return canonicalize_url(url, self._strip_params)

    def validate_url(self, url: str) -> bool:
        """Validate that a URL has http(s) scheme.

        Args:
            url: The URL to validate.

        Returns:
            True if URL is valid.
        """
        return url.startswith(("http://", "https://"))

    def truncate_raw_json(
        self,
        data: Mapping[str, Any],
    ) -> tuple[str, bool]:
        """Serialize and truncate raw_json if needed.

        Args:
            data: Data dictionary to serialize.

        Returns:
            Tuple of (json_string, was_truncated).
        """
        # Remove any sensitive keys
        sanitized = self._sanitize_raw_json(data)

        # Serialize with stable ordering
        json_str = json.dumps(sanitized, sort_keys=True, ensure_ascii=False)

        # Check size
        if len(json_str.encode("utf-8")) <= RAW_JSON_MAX_SIZE:
            return json_str, False

        # Truncate and add marker
        sanitized["raw_truncated"] = True
        # Remove large fields first
        for key in ["abstract", "content", "body", "description"]:
            field_value = sanitized.get(key)
            if isinstance(field_value, str):
                sanitized[key] = field_value[:500] + "..."

        json_str = json.dumps(sanitized, sort_keys=True, ensure_ascii=False)

        # If still too large, truncate harder
        while len(json_str.encode("utf-8")) > RAW_JSON_MAX_SIZE:
            # Find largest string field and truncate it
            truncated = False
            for key, value in list(sanitized.items()):
                if isinstance(value, str) and len(value) > FIELD_TRUNCATION_THRESHOLD:
                    sanitized[key] = value[:FIELD_TRUNCATION_THRESHOLD] + "..."
                    truncated = True
                    break
            if not truncated:
                break
            json_str = json.dumps(sanitized, sort_keys=True, ensure_ascii=False)

        return json_str, True

    def _sanitize_raw_json(
        self,
        data: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Remove sensitive keys from raw_json data.

        Args:
            data: Data dictionary to sanitize.

        Returns:
            Sanitized data dictionary.
        """
        sensitive_keys = {
            "authorization",
            "auth",
            "token",
            "api_key",
            "apikey",
            "secret",
            "password",
            "cookie",
            "session",
        }

        return {
            key: value
            for key, value in data.items()
            if key.lower() not in sensitive_keys
        }

    def sort_items_deterministically(self, items: list[Item]) -> list[Item]:
        """Sort items in deterministic order.

        Order: published_at DESC (nulls last), url ASC

        Args:
            items: List of items to sort.

        Returns:
            Sorted list of items.
        """

        def sort_key(item: Item) -> tuple[int, float, str]:
            """Create sort key for ascending sort.

            Returns tuple where:
            - First element: 0 for dated items (first), 1 for nulls (last)
            - Second element: negative timestamp (so newer = more negative = first)
            - Third element: URL for alphabetical tie-breaking
            """
            if item.published_at is None:
                # Nulls go last: priority 1, no timestamp needed
                return (1, 0.0, item.url)
            # Dated items come first (priority 0), newer dates have larger timestamps
            # Use negative so larger timestamps (newer) sort first
            return (0, -item.published_at.timestamp(), item.url)

        return sorted(items, key=sort_key)

    def enforce_max_items(
        self,
        items: list[Item],
        max_items: int,
    ) -> list[Item]:
        """Enforce max_items_per_source limit.

        Items should already be sorted deterministically.

        Args:
            items: List of items (already sorted).
            max_items: Maximum number of items to keep.

        Returns:
            Truncated list of items.
        """
        if max_items <= 0:
            return items
        return items[:max_items]

    def filter_items_by_time(
        self,
        items: list[Item],
        now: datetime,
        lookback_hours: int = 24,
        source_id: str = "",
    ) -> list[Item]:
        """Filter items to only include those published within the lookback window.

        This method filters items at collection time to ensure only recently
        published content is collected. Items without a published_at date
        are excluded.

        Args:
            items: List of items to filter.
            now: Current timestamp (typically run start time).
            lookback_hours: Number of hours to look back (default 24).
            source_id: Source ID for logging.

        Returns:
            Filtered list of items published within the lookback window.
        """
        log = structlog.get_logger().bind(
            component="collector",
            source_id=source_id,
        )

        # Calculate cutoff time
        cutoff = now - timedelta(hours=lookback_hours)

        # Ensure cutoff is timezone-aware (UTC)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)

        original_count = len(items)
        filtered_items = []

        for item in items:
            if item.published_at is None:
                # Skip items without published_at
                continue

            # Ensure item's published_at is timezone-aware
            item_published = item.published_at
            if item_published.tzinfo is None:
                item_published = item_published.replace(tzinfo=UTC)

            if item_published >= cutoff:
                filtered_items.append(item)

        filtered_count = len(filtered_items)
        dropped_count = original_count - filtered_count

        log.info(
            "time_filter_applied",
            lookback_hours=lookback_hours,
            cutoff=cutoff.isoformat(),
            original_count=original_count,
            filtered_count=filtered_count,
            dropped_count=dropped_count,
        )

        return filtered_items
