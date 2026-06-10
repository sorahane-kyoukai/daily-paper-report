"""OpenReview venue collector.

This module provides a collector for OpenReview venue papers,
capturing paper titles, submission dates, forum URLs, and PDF URLs.
"""

import json
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import structlog

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import CollectorErrorClass, ErrorRecord
from src.collectors.platform.constants import (
    AUTH_ERROR_HINTS,
    FIELD_FORUM_ID,
    FIELD_LAST_MODIFIED,
    FIELD_PDF_URL,
    FIELD_PLATFORM,
    OPENREVIEW_API_BASE_URL,
    OPENREVIEW_API_NOTES_PATH,
    OPENREVIEW_DEFAULT_MAX_QPS,
    PLATFORM_OPENREVIEW,
)
from src.collectors.platform.helpers import (
    build_pdf_url,
    extract_nested_value,
    get_auth_token,
    is_auth_error,
)
from src.collectors.platform.metrics import PlatformMetrics
from src.collectors.platform.rate_limiter import (
    TokenBucketRateLimiter,
    get_platform_rate_limiter,
)
from src.collectors.state_machine import SourceState, SourceStateMachine
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.hash import compute_content_hash
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()

# Regex to extract venue ID from OpenReview URL
OPENREVIEW_VENUE_PATTERN = re.compile(r"openreview\.net/group\?id=(?P<venue_id>[^&]+)")


def extract_venue_id(url: str, query: str | None = None) -> str | None:
    """Extract venue ID from an OpenReview URL or query field.

    Args:
        url: OpenReview venue URL.
        query: Optional query field containing venue_id.

    Returns:
        Venue ID or None if not found.
    """
    # First check the query field (preferred)
    if query:
        return query

    # Try to extract from URL
    match = OPENREVIEW_VENUE_PATTERN.search(url)
    if match:
        return match.group("venue_id")
    return None


class OpenReviewVenueCollector(BaseCollector):
    """Collector for OpenReview venue papers.

    Lists notes/papers for a given venue_id and ingests:
    - Paper title
    - Submission date / last update
    - Forum URL
    - PDF URL (when provided)

    Canonical URL is the forum URL.

    API documentation: https://api2.openreview.net/
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        """Initialize the OpenReview venue collector.

        Args:
            strip_params: URL parameters to strip (not used for OpenReview).
            run_id: Run identifier for logging.
            rate_limiter: Optional rate limiter for dependency injection.
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._metrics = PlatformMetrics.get_instance()
        self._rate_limiter = rate_limiter or get_platform_rate_limiter(
            PLATFORM_OPENREVIEW, OPENREVIEW_DEFAULT_MAX_QPS
        )

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect papers from an OpenReview venue.

        Args:
            source_config: Configuration for the source.
            http_client: HTTP client for fetching.
            now: Current timestamp for time-based filtering.

        Returns:
            CollectorResult with items and status.
        """
        self._now = now  # Store for use in filtering
        self._lookback_hours = lookback_hours
        log = logger.bind(
            component="platform",
            platform=PLATFORM_OPENREVIEW,
            run_id=self._run_id,
            source_id=source_config.id,
        )

        state_machine = SourceStateMachine(
            source_id=source_config.id,
            run_id=self._run_id,
        )

        parse_warnings: list[str] = []

        try:
            state_machine.to_fetching()

            # Extract venue_id from URL or query
            venue_id = extract_venue_id(source_config.url, source_config.query)
            if not venue_id:
                log.warning("invalid_openreview_url", url=source_config.url)
                state_machine.to_failed()
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.SCHEMA,
                        message=(
                            f"Invalid OpenReview venue URL or missing query field: "
                            f"{source_config.url}. Use 'query' field to specify venue_id "
                            f"(e.g., 'ICLR.cc/2025/Conference/-/Blind_Submission')."
                        ),
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )
            api_url = self._build_api_url(
                venue_id,
                self.resolve_fetch_limit(
                    max_items=max_items, fallback_limit=1000, api_cap=1000
                ),
            )

            log.info(
                "fetching_papers",
                venue_id=venue_id,
            )

            # Acquire rate limit token
            self._rate_limiter.acquire()

            # Build headers with auth if available
            headers = self._build_headers()

            # Fetch notes
            start_time = time.monotonic()
            result = http_client.fetch(
                source_id=source_config.id,
                url=api_url,
                extra_headers=headers,
            )
            duration_ms = (time.monotonic() - start_time) * 1000
            self._metrics.record_api_call(PLATFORM_OPENREVIEW)

            # Check for auth errors
            if result.error:
                if is_auth_error(result):
                    remediation = AUTH_ERROR_HINTS[PLATFORM_OPENREVIEW]
                    log.warning(
                        "auth_error",
                        status_code=result.status_code,
                        remediation=remediation,
                    )
                    self._metrics.record_error(PLATFORM_OPENREVIEW, "auth")
                    state_machine.to_failed()
                    return CollectorResult(
                        items=[],
                        error=ErrorRecord(
                            error_class=CollectorErrorClass.FETCH,
                            message=f"Authentication failed (HTTP {result.status_code}). {remediation}",
                            source_id=source_config.id,
                        ),
                        state=SourceState.SOURCE_FAILED,
                    )

                log.warning(
                    "fetch_failed",
                    error_class=result.error.error_class.value,
                    status_code=result.status_code,
                )
                self._metrics.record_error(PLATFORM_OPENREVIEW, "fetch")
                state_machine.to_failed()
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.FETCH,
                        message=str(result.error.message),
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            state_machine.to_parsing()

            # Parse JSON response
            items = self._parse_notes(
                body=result.body_bytes,
                source_config=source_config,
                venue_id=venue_id,
                parse_warnings=parse_warnings,
            )

            if not items:
                log.info("empty_response")
                state_machine.to_done()
                return CollectorResult(
                    items=[],
                    parse_warnings=parse_warnings,
                    state=SourceState.SOURCE_DONE,
                )

            # Filter by time: only keep items published in the last 24 hours
            items = self.filter_items_by_time(
                items=items,
                now=self._now,
                lookback_hours=self._lookback_hours,
                source_id=source_config.id,
            )

            items = self.sort_items_deterministically(items)
            items = self.enforce_max_items(items, max_items)

            self._metrics.record_items(PLATFORM_OPENREVIEW, len(items))

            # Check if we were rate limited
            rate_limited = self._rate_limiter.was_rate_limited

            log.info(
                "collection_complete",
                items_emitted=len(items),
                venue_id=venue_id,
                request_count=1,
                rate_limited=rate_limited,
                duration_ms=round(duration_ms, 2),
            )

            state_machine.to_done()
            return CollectorResult(
                items=items,
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_DONE,
            )

        except Exception as e:  # noqa: BLE001
            log.warning("unexpected_error", error=str(e))
            self._metrics.record_error(PLATFORM_OPENREVIEW, "parse")
            state_machine.to_failed()
            return CollectorResult(
                items=[],
                error=ErrorRecord(
                    error_class=CollectorErrorClass.PARSE,
                    message=f"Unexpected error: {e}",
                    source_id=source_config.id,
                ),
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_FAILED,
            )

    def _build_api_url(self, venue_id: str, limit: int) -> str:
        """Build OpenReview API URL for notes.

        Args:
            venue_id: Venue invitation ID.
            limit: Number of notes to fetch.

        Returns:
            Full API URL.
        """
        params = {
            "invitation": venue_id,
            "limit": min(limit, 1000),  # API limit
            "sort": "cdate:desc",  # Sort by creation date descending
        }
        return (
            f"{OPENREVIEW_API_BASE_URL}{OPENREVIEW_API_NOTES_PATH}?{urlencode(params)}"
        )

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with optional auth.

        Returns:
            Headers dictionary.
        """
        headers: dict[str, str] = {
            "Accept": "application/json",
        }

        token = get_auth_token(PLATFORM_OPENREVIEW)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return headers

    def _parse_notes(
        self,
        body: bytes,
        source_config: SourceConfig,
        venue_id: str,
        parse_warnings: list[str],
    ) -> list[Item]:
        """Parse OpenReview notes JSON response.

        Args:
            body: Response body bytes.
            source_config: Source configuration.
            venue_id: Venue ID.
            parse_warnings: List to append warnings to.

        Returns:
            List of parsed items.
        """
        items: list[Item] = []

        try:
            response = json.loads(body)
        except json.JSONDecodeError as e:
            parse_warnings.append(f"Failed to parse JSON response: {e}")
            return []

        # Notes can be in 'notes' key or at root level
        notes = (
            response.get("notes", response) if isinstance(response, dict) else response
        )
        if not isinstance(notes, list):
            parse_warnings.append("Expected array of notes")
            return []

        for note in notes:
            try:
                item = self._parse_note(note, source_config, venue_id)
                if item:
                    items.append(item)
            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to parse note: {e}")

        return items

    def _parse_note(
        self,
        note: dict[str, Any],
        source_config: SourceConfig,
        venue_id: str,
    ) -> Item | None:
        """Parse a single note object.

        Args:
            note: Note JSON object.
            source_config: Source configuration.
            venue_id: Venue ID.

        Returns:
            Item if parsing succeeded, None otherwise.
        """
        # Extract required fields
        forum_id = note.get("forum") or note.get("id")
        if not forum_id:
            return None

        # Build canonical URL
        canonical_url = f"https://openreview.net/forum?id={forum_id}"

        # Extract title from content using helper
        content = note.get("content", {})
        title = extract_nested_value(content.get("title"))
        if not title:
            title = f"Paper {forum_id}"

        # Extract dates
        published_at = None
        date_confidence = DateConfidence.LOW

        # Try mdate (modification date) first, then cdate (creation date)
        mdate = note.get("mdate")
        cdate = note.get("cdate")
        timestamp = mdate or cdate

        if timestamp:
            try:
                # OpenReview uses millisecond timestamps
                if isinstance(timestamp, int | float):
                    published_at = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
                    date_confidence = DateConfidence.HIGH
                elif isinstance(timestamp, str):
                    published_at = datetime.fromisoformat(
                        timestamp.replace("Z", "+00:00")
                    )
                    date_confidence = DateConfidence.HIGH
            except (ValueError, OSError):
                pass

        # Build raw_json
        raw_data = self._build_raw_data(note, venue_id)
        raw_json, _ = self.truncate_raw_json(raw_data)

        # Compute content hash
        content_hash = self._compute_content_hash(note, canonical_url)

        return Item(
            url=canonical_url,
            source_id=source_config.id,
            tier=source_config.tier,
            kind=source_config.kind.value,
            title=title,
            published_at=published_at,
            date_confidence=date_confidence,
            content_hash=content_hash,
            raw_json=raw_json,
        )

    def _build_raw_data(
        self,
        note: dict[str, Any],
        venue_id: str,
    ) -> dict[str, Any]:
        """Build raw_json data from note.

        Args:
            note: Note JSON object.
            venue_id: Venue ID.

        Returns:
            Dictionary of raw metadata.
        """
        raw_data: dict[str, Any] = {
            FIELD_PLATFORM: PLATFORM_OPENREVIEW,
            "venue_id": venue_id,
        }

        forum_id = note.get("forum") or note.get("id")
        if forum_id:
            raw_data[FIELD_FORUM_ID] = forum_id

        # Extract modification date
        if note.get("mdate"):
            raw_data[FIELD_LAST_MODIFIED] = note["mdate"]

        # Extract PDF URL using helper
        content = note.get("content", {})
        pdf_url = build_pdf_url(content.get("pdf"), forum_id or "")
        if pdf_url:
            raw_data[FIELD_PDF_URL] = pdf_url

        # Extract title using helper
        title = extract_nested_value(content.get("title"))
        if title:
            raw_data["title"] = title

        # Extract authors using helper
        authors = extract_nested_value(content.get("authors"))
        if authors and isinstance(authors, list):
            raw_data["authors"] = authors

        # Include creation date
        if note.get("cdate"):
            raw_data["cdate"] = note["cdate"]

        return raw_data

    def _compute_content_hash(
        self,
        note: dict[str, Any],
        canonical_url: str,
    ) -> str:
        """Compute content hash for note.

        Hash is computed from: title, mdate (last modified).

        Args:
            note: Note JSON object.
            canonical_url: Canonical URL.

        Returns:
            Content hash string.
        """
        content = note.get("content", {})
        title = extract_nested_value(content.get("title")) or ""

        extra: dict[str, str] = {}

        if note.get("mdate"):
            extra["mdate"] = str(note["mdate"])

        return compute_content_hash(
            title=title,
            url=canonical_url,
            extra=extra if extra else None,
        )
