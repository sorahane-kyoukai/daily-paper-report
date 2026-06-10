"""Cache management for HTTP fetch operations.

Encapsulates all cache-related logic for conditional requests (ETag/Last-Modified).
"""

from datetime import UTC, datetime
from typing import Protocol

import structlog

from src.features.fetch.constants import HTTP_STATUS_NOT_MODIFIED
from src.features.fetch.models import FetchResult
from src.features.store.models import HttpCacheEntry


logger = structlog.get_logger()


class CacheStore(Protocol):
    """Protocol for cache storage operations.

    Abstracts the storage layer to enable testing and alternative implementations.
    """

    def get_http_cache(self, source_id: str) -> HttpCacheEntry | None:
        """Retrieve cached HTTP metadata for a source.

        Args:
            source_id: Unique identifier for the source.

        Returns:
            Cached entry if exists, None otherwise.
        """
        ...

    def upsert_http_cache_headers(self, entry: HttpCacheEntry) -> None:
        """Store or update HTTP cache metadata.

        Args:
            entry: Cache entry to store.
        """
        ...


class CacheManager:
    """Manages HTTP cache operations for conditional requests.

    Encapsulates the logic for:
    - Building conditional request headers (If-None-Match, If-Modified-Since)
    - Updating cache entries after fetch operations
    - Preserving existing cache headers on 304 responses
    """

    def __init__(self, store: CacheStore, run_id: str) -> None:
        """Initialize the cache manager.

        Args:
            store: Storage backend for cache entries.
            run_id: Unique run identifier for logging.
        """
        self._store = store
        self._log = logger.bind(component="cache", run_id=run_id)

    def get_conditional_headers(self, source_id: str) -> dict[str, str]:
        """Get conditional request headers from cached data.

        Args:
            source_id: Source identifier to look up.

        Returns:
            Dictionary with If-None-Match and/or If-Modified-Since headers.
        """
        cache_entry = self._store.get_http_cache(source_id)
        headers: dict[str, str] = {}

        if cache_entry:
            if cache_entry.etag:
                headers["If-None-Match"] = cache_entry.etag
            if cache_entry.last_modified:
                headers["If-Modified-Since"] = cache_entry.last_modified
            self._log.debug(
                "cache_lookup",
                source_id=source_id,
                has_etag=cache_entry.etag is not None,
                has_last_modified=cache_entry.last_modified is not None,
            )

        return headers

    def update_from_result(self, source_id: str, result: FetchResult) -> None:
        """Update cache from a fetch result.

        For successful responses (2xx), stores ETag and Last-Modified headers.
        For 304 responses, preserves existing cache headers.
        For errors, only updates last_status for tracking.

        Args:
            source_id: Source identifier.
            result: Fetch result to cache.
        """
        # Error case (not 304): only track status
        if result.error is not None and result.status_code != HTTP_STATUS_NOT_MODIFIED:
            entry = HttpCacheEntry(
                source_id=source_id,
                etag=None,
                last_modified=None,
                last_status=result.status_code if result.status_code > 0 else None,
                last_fetch_at=datetime.now(UTC),
            )
            self._store.upsert_http_cache_headers(entry)
            return

        # Extract cache headers from response
        etag = result.headers.get("etag") or result.headers.get("ETag")
        last_modified = result.headers.get("last-modified") or result.headers.get(
            "Last-Modified"
        )

        # For 304, preserve existing cache headers
        if result.status_code == HTTP_STATUS_NOT_MODIFIED:
            existing = self._store.get_http_cache(source_id)
            if existing:
                etag = etag or existing.etag
                last_modified = last_modified or existing.last_modified

        entry = HttpCacheEntry(
            source_id=source_id,
            etag=etag,
            last_modified=last_modified,
            last_status=result.status_code,
            last_fetch_at=datetime.now(UTC),
        )
        self._store.upsert_http_cache_headers(entry)

        self._log.debug(
            "cache_update",
            source_id=source_id,
            status_code=result.status_code,
            etag=etag is not None,
            last_modified=last_modified is not None,
        )

    def get_cached_status(self, source_id: str) -> int | None:
        """Get the last HTTP status for a source.

        Args:
            source_id: Source identifier.

        Returns:
            Last HTTP status code, or None if not cached.
        """
        cache_entry = self._store.get_http_cache(source_id)
        return cache_entry.last_status if cache_entry else None
