"""RSS/Atom feed collector."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import mktime

import feedparser  # type: ignore[import-untyped]
import structlog

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import (
    CollectorErrorClass,
    ErrorRecord,
    ParseError,
)
from src.collectors.state_machine import SourceState, SourceStateMachine
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.hash import compute_content_hash
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()


class RssAtomCollector(BaseCollector):
    """Collector for RSS and Atom feeds.

    Parses standard RSS 2.0 and Atom 1.0 feeds using feedparser.
    Extracts title, link, published date, and summary/description.
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
    ) -> None:
        """Initialize the RSS/Atom collector.

        Args:
            strip_params: URL parameters to strip for canonicalization.
            run_id: Run identifier for logging.
        """
        super().__init__(strip_params)
        self._run_id = run_id

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect items from an RSS/Atom feed.

        Args:
            source_config: Configuration for the source.
            http_client: HTTP client for fetching.
            now: Current timestamp for consistency.

        Returns:
            CollectorResult with items and status.
        """
        log = logger.bind(
            component="collector",
            run_id=self._run_id,
            source_id=source_config.id,
            method="rss_atom",
        )

        state_machine = SourceStateMachine(
            source_id=source_config.id,
            run_id=self._run_id,
        )

        parse_warnings: list[str] = []

        try:
            # Transition to fetching
            state_machine.to_fetching()

            # Fetch the feed
            result = http_client.fetch(
                source_id=source_config.id,
                url=source_config.url,
                extra_headers=source_config.headers or None,
            )

            if result.error:
                log.warning(
                    "fetch_failed",
                    error_class=result.error.error_class.value
                    if hasattr(result.error, "error_class")
                    else "unknown",
                    status_code=result.status_code,
                )
                state_machine.to_failed()
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.FETCH,
                        message=str(result.error),
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            # Handle 304 Not Modified
            if result.cache_hit:
                log.info("cache_hit_no_changes")
                state_machine.to_parsing()
                state_machine.to_done()
                return CollectorResult(
                    items=[],
                    state=SourceState.SOURCE_DONE,
                )

            # Transition to parsing
            state_machine.to_parsing()

            # Parse the feed
            feed = feedparser.parse(result.body_bytes)

            if feed.bozo and feed.bozo_exception:
                # Feed had parsing issues but may still be usable
                parse_warnings.append(f"Feed parsing warning: {feed.bozo_exception}")
                log.warning(
                    "feed_parse_warning",
                    bozo_exception=str(feed.bozo_exception),
                )

            if not feed.entries:
                log.info("empty_feed")
                state_machine.to_done()
                return CollectorResult(
                    items=[],
                    parse_warnings=parse_warnings,
                    state=SourceState.SOURCE_DONE,
                )

            # Parse entries
            items = self._parse_entries(
                entries=feed.entries,
                source_config=source_config,
                base_url=source_config.url,
                parse_warnings=parse_warnings,
            )

            # Filter by time: only keep items published in the last 24 hours
            items = self.filter_items_by_time(
                items=items,
                now=now,
                lookback_hours=lookback_hours,
                source_id=source_config.id,
            )

            # Sort deterministically
            items = self.sort_items_deterministically(items)

            # Enforce max_items
            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )
            items = self.enforce_max_items(items, max_items)

            log.info(
                "collection_complete",
                items_emitted=len(items),
                parse_warnings_count=len(parse_warnings),
            )

            state_machine.to_done()
            return CollectorResult(
                items=items,
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_DONE,
            )

        except ParseError as e:
            log.warning("parse_error", error=str(e))
            state_machine.to_failed()
            return CollectorResult(
                items=[],
                error=ErrorRecord.from_exception(e),
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_FAILED,
            )

        except Exception as e:  # noqa: BLE001
            log.warning("unexpected_error", error=str(e))
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

    def _parse_entries(
        self,
        entries: list[feedparser.FeedParserDict],
        source_config: SourceConfig,
        base_url: str,
        parse_warnings: list[str],
    ) -> list[Item]:
        """Parse feed entries into Items.

        Args:
            entries: List of feedparser entries.
            source_config: Source configuration.
            base_url: Base URL for resolving relative links.
            parse_warnings: List to append warnings to.

        Returns:
            List of parsed Items.
        """
        items: list[Item] = []

        for entry in entries:
            try:
                item = self._parse_single_entry(
                    entry=entry,
                    source_config=source_config,
                    base_url=base_url,
                )
                if item:
                    items.append(item)
            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to parse entry: {e}")

        return items

    def _parse_single_entry(  # noqa: C901
        self,
        entry: feedparser.FeedParserDict,
        source_config: SourceConfig,
        base_url: str,
    ) -> Item | None:
        """Parse a single feed entry.

        Args:
            entry: Feedparser entry dict.
            source_config: Source configuration.
            base_url: Base URL for resolving relative links.

        Returns:
            Item if parsing succeeded, None otherwise.
        """
        # Extract link
        link = entry.get("link", "")
        if not link:
            # Try alternate links
            links = entry.get("links", [])
            for link_entry in links:
                if link_entry.get("rel") == "alternate":
                    link = link_entry.get("href", "")
                    break
            if not link and links:
                link = links[0].get("href", "")

        if not link:
            return None

        # Canonicalize URL
        canonical_url = self.canonicalize_url(link, base_url)

        # Validate URL
        if not self.validate_url(canonical_url):
            return None

        # Extract title
        title = entry.get("title", "").strip()
        if not title:
            title = f"Untitled from {source_config.name}"

        # Extract published date
        published_at, date_confidence = self._extract_date(entry)

        # Build raw_json
        raw_data: dict[str, str | int | float | bool | list[str] | None] = {
            "original_link": link,
            "title": title,
            "source_name": source_config.name,
        }

        # Add summary/description if available
        summary = entry.get("summary", "") or entry.get("description", "")
        if summary:
            raw_data["summary"] = summary[:1000]  # Truncate for storage

        # Add author if available
        author = entry.get("author", "")
        if author:
            raw_data["author"] = author

        # Add categories/tags if available
        tags = entry.get("tags", [])
        if tags:
            raw_data["categories"] = [t.get("term", "") for t in tags if t.get("term")]

        # Truncate raw_json if needed
        raw_json, was_truncated = self.truncate_raw_json(raw_data)

        # Compute content hash
        content_hash = compute_content_hash(
            title=title,
            url=canonical_url,
            published_at=published_at,
            extra={"summary": summary[:200]} if summary else None,
        )

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

    def _extract_date(
        self,
        entry: feedparser.FeedParserDict,
    ) -> tuple[datetime | None, DateConfidence]:
        """Extract publication date from entry.

        Args:
            entry: Feedparser entry dict.

        Returns:
            Tuple of (datetime or None, confidence level).
        """
        # Try published_parsed first (most reliable)
        if entry.get("published_parsed"):
            try:
                timestamp = mktime(entry.published_parsed)
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
                return dt, DateConfidence.HIGH
            except (ValueError, OverflowError):
                pass

        # Try updated_parsed
        if entry.get("updated_parsed"):
            try:
                timestamp = mktime(entry.updated_parsed)
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
                return dt, DateConfidence.MEDIUM
            except (ValueError, OverflowError):
                pass

        # Try parsing published string
        if entry.get("published"):
            try:
                dt = parsedate_to_datetime(entry.published)
                return dt.astimezone(UTC), DateConfidence.HIGH
            except (ValueError, TypeError):
                pass

        # Try parsing updated string
        if entry.get("updated"):
            try:
                dt = parsedate_to_datetime(entry.updated)
                return dt.astimezone(UTC), DateConfidence.MEDIUM
            except (ValueError, TypeError):
                pass

        # No date found
        return None, DateConfidence.LOW
