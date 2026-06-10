"""Item page fetcher for date recovery with K-cap enforcement."""

from dataclasses import dataclass, field
from urllib.parse import urlparse

import structlog

from src.collectors.html_profile.date_extractor import (
    DateExtractionResult,
    DateExtractor,
)
from src.collectors.html_profile.metrics import HtmlProfileMetrics
from src.collectors.html_profile.models import DomainProfile
from src.features.fetch.client import HttpFetcher
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()


@dataclass
class ItemPageFetchResult:
    """Result of item page fetch and date extraction.

    Attributes:
        url: URL of the item page.
        fetched: Whether the page was fetched.
        date_result: Date extraction result, if successful.
        error: Error message if fetch failed.
        content_type: Content-Type of the response.
    """

    url: str
    fetched: bool
    date_result: DateExtractionResult | None = None
    error: str | None = None
    content_type: str | None = None


@dataclass
class ItemPageRecoveryReport:
    """Report of item page date recovery.

    Attributes:
        domain: Domain that was processed.
        items_needing_recovery: Number of items that needed date recovery.
        pages_fetched: Number of item pages actually fetched.
        dates_recovered: Number of dates successfully recovered.
        fetch_results: Individual fetch results.
    """

    domain: str
    items_needing_recovery: int
    pages_fetched: int
    dates_recovered: int
    fetch_results: list[ItemPageFetchResult] = field(default_factory=list)


class ItemPageFetcher:
    """Fetches item pages for date recovery with K-cap enforcement.

    Security features:
    - Enforces max item pages per run (K-cap)
    - Validates content-type
    - Blocks cross-domain redirects unless allowlisted
    - Never downloads binary assets
    """

    # Content types that indicate binary data (to reject)
    BINARY_CONTENT_TYPES = frozenset(
        [
            "image/",
            "video/",
            "audio/",
            "application/octet-stream",
            "application/pdf",
            "application/zip",
        ]
    )

    def __init__(
        self,
        http_client: HttpFetcher,
        profile: DomainProfile,
        run_id: str = "",
    ) -> None:
        """Initialize the item page fetcher.

        Args:
            http_client: HTTP client for fetching.
            profile: Domain profile with settings.
            run_id: Run identifier for logging.
        """
        self._http_client = http_client
        self._profile = profile
        self._run_id = run_id
        self._metrics = HtmlProfileMetrics.get_instance()
        self._date_extractor = DateExtractor(profile.date_rules, run_id)
        self._log = logger.bind(
            component="html_profile",
            run_id=run_id,
            domain=profile.domain,
        )

    def recover_dates_for_items(
        self,
        items: list[Item],
        source_id: str,
    ) -> tuple[list[Item], ItemPageRecoveryReport]:
        """Recover dates for items with low confidence.

        Fetches up to K item pages to extract dates, where K is defined
        by profile.max_item_page_fetches.

        Args:
            items: List of items to process.
            source_id: Source identifier for logging.

        Returns:
            Tuple of (updated items list, recovery report).
        """
        domain = self._profile.domain

        # Find items needing date recovery
        items_needing_recovery = [
            (i, item)
            for i, item in enumerate(items)
            if item.date_confidence == DateConfidence.LOW and item.published_at is None
        ]

        report = ItemPageRecoveryReport(
            domain=domain,
            items_needing_recovery=len(items_needing_recovery),
            pages_fetched=0,
            dates_recovered=0,
        )

        if not items_needing_recovery:
            self._log.debug(
                "no_items_need_recovery",
                source_id=source_id,
                total_items=len(items),
            )
            return items, report

        # Don't proceed if item page recovery is disabled
        if not self._profile.enable_item_page_recovery:
            self._log.debug(
                "item_page_recovery_disabled",
                source_id=source_id,
                items_needing=len(items_needing_recovery),
            )
            return items, report

        # Apply K-cap
        k_cap = self._profile.max_item_page_fetches
        items_to_fetch = items_needing_recovery[:k_cap]

        self._log.info(
            "recovering_dates",
            source_id=source_id,
            items_needing=len(items_needing_recovery),
            items_to_fetch=len(items_to_fetch),
            k_cap=k_cap,
        )

        # Make a mutable copy of the items list
        updated_items = list(items)

        for idx, item in items_to_fetch:
            fetch_result = self._fetch_and_extract_date(item.url, source_id)
            report.fetch_results.append(fetch_result)

            if fetch_result.fetched:
                report.pages_fetched += 1

            if fetch_result.date_result and fetch_result.date_result.published_at:
                report.dates_recovered += 1

                # Update item with recovered date
                updated_items[idx] = Item(
                    url=item.url,
                    source_id=item.source_id,
                    tier=item.tier,
                    kind=item.kind,
                    title=item.title,
                    published_at=fetch_result.date_result.published_at,
                    date_confidence=fetch_result.date_result.confidence,
                    content_hash=item.content_hash,
                    raw_json=self._update_raw_json(
                        item.raw_json,
                        fetch_result.date_result,
                    ),
                    first_seen_at=item.first_seen_at,
                    last_seen_at=item.last_seen_at,
                )

        # Record metrics
        self._metrics.record_item_pages_fetched(domain, report.pages_fetched)
        self._metrics.record_date_recovery(domain, report.dates_recovered)

        self._log.info(
            "date_recovery_complete",
            source_id=source_id,
            pages_fetched=report.pages_fetched,
            dates_recovered=report.dates_recovered,
        )

        return updated_items, report

    def _fetch_and_extract_date(
        self,
        url: str,
        source_id: str,
    ) -> ItemPageFetchResult:
        """Fetch an item page and extract the date.

        Args:
            url: URL to fetch.
            source_id: Source identifier.

        Returns:
            ItemPageFetchResult with date extraction result.
        """
        log = self._log.bind(url=url)

        # Validate URL before fetching
        parsed = urlparse(url)
        target_domain = parsed.netloc

        # Check cross-domain redirect allowlist
        if not self._profile.is_redirect_allowed(self._profile.domain, target_domain):
            log.warning(
                "cross_domain_blocked",
                target_domain=target_domain,
            )
            return ItemPageFetchResult(
                url=url,
                fetched=False,
                error=f"Cross-domain fetch blocked: {target_domain}",
            )

        try:
            result = self._http_client.fetch(
                source_id=source_id,
                url=url,
            )

            if result.error:
                log.debug(
                    "item_fetch_failed",
                    error=str(result.error),
                )
                return ItemPageFetchResult(
                    url=url,
                    fetched=False,
                    error=str(result.error),
                )

            # Validate content-type
            content_type = result.headers.get("content-type", "")

            if not self._profile.is_content_type_allowed(content_type):
                log.debug(
                    "content_type_rejected",
                    content_type=content_type,
                )
                return ItemPageFetchResult(
                    url=url,
                    fetched=True,
                    content_type=content_type,
                    error=f"Content-Type not allowed: {content_type}",
                )

            # Check for binary content types
            if self._is_binary_content(content_type):
                log.debug(
                    "binary_content_rejected",
                    content_type=content_type,
                )
                return ItemPageFetchResult(
                    url=url,
                    fetched=True,
                    content_type=content_type,
                    error=f"Binary content type rejected: {content_type}",
                )

            # Extract date from HTML
            html = result.body_bytes.decode("utf-8", errors="replace")
            date_result = self._date_extractor.extract_from_html(html)

            log.debug(
                "date_extraction_complete",
                found=date_result.published_at is not None,
                method=date_result.method.value,
            )

            return ItemPageFetchResult(
                url=url,
                fetched=True,
                content_type=content_type,
                date_result=date_result,
            )

        except Exception as e:  # noqa: BLE001
            log.warning(
                "item_fetch_exception",
                error=str(e),
            )
            return ItemPageFetchResult(
                url=url,
                fetched=False,
                error=str(e),
            )

    def _is_binary_content(self, content_type: str) -> bool:
        """Check if content type indicates binary data.

        Args:
            content_type: Content-Type header value.

        Returns:
            True if content appears to be binary.
        """
        mime_type = content_type.split(";")[0].strip().lower()
        return any(mime_type.startswith(prefix) for prefix in self.BINARY_CONTENT_TYPES)

    def _update_raw_json(
        self,
        raw_json: str,
        date_result: DateExtractionResult,
    ) -> str:
        """Update raw_json with date recovery information.

        Args:
            raw_json: Original raw_json string.
            date_result: Date extraction result.

        Returns:
            Updated raw_json string.
        """
        import json

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            data = {}

        data["date_recovered_from_item_page"] = True
        data["extraction_method"] = date_result.method.value
        if date_result.raw_date:
            data["extracted_date_raw"] = date_result.raw_date
        data["candidate_dates"] = date_result.candidate_dates

        return json.dumps(data, sort_keys=True, ensure_ascii=False)
