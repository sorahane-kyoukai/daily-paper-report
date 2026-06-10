"""HTML list page collector with domain profile support."""

import re
import time
from datetime import datetime
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup, Tag

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import (
    CollectorErrorClass,
    ErrorRecord,
    ParseError,
)
from src.collectors.html_profile.date_extractor import DateExtractor
from src.collectors.html_profile.item_fetcher import ItemPageFetcher
from src.collectors.html_profile.metrics import HtmlProfileMetrics
from src.collectors.html_profile.models import DomainProfile
from src.collectors.html_profile.registry import ProfileRegistry
from src.collectors.state_machine import SourceState, SourceStateMachine
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.hash import compute_content_hash
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()


# Minimum title length for link extraction
MIN_TITLE_LENGTH = 5

# Minimum description length
MIN_DESCRIPTION_LENGTH = 20


class HtmlListCollector(BaseCollector):
    """Collector for HTML list pages with domain profile support.

    Extracts links from list pages (blog indexes, news lists, etc.)
    with best-effort date extraction. Supports item-page date recovery
    for items with low date confidence.

    Features:
    - Domain-specific extraction rules via profiles
    - Date extraction with precedence (time > meta > JSON-LD > text)
    - Item-page date recovery with K-cap
    - Security: content-type validation, cross-domain blocking
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
        profile_registry: ProfileRegistry | None = None,
    ) -> None:
        """Initialize the HTML list collector.

        Args:
            strip_params: URL parameters to strip for canonicalization.
            run_id: Run identifier for logging.
            profile_registry: Optional profile registry (uses singleton if not provided).
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._registry = profile_registry or ProfileRegistry.get_instance()
        self._metrics = HtmlProfileMetrics.get_instance()

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect items from an HTML list page.

        Args:
            source_config: Configuration for the source.
            http_client: HTTP client for fetching.
            now: Current timestamp for consistency (kept for interface).

        Returns:
            CollectorResult with items and status.
        """
        self._now = now  # Store for time-based filtering
        self._lookback_hours = lookback_hours
        start_time = time.perf_counter_ns()
        domain = urlparse(source_config.url).netloc

        log = logger.bind(
            component="html_profile",
            run_id=self._run_id,
            source_id=source_config.id,
            method="html_list",
            domain=domain,
        )

        state_machine = SourceStateMachine(
            source_id=source_config.id,
            run_id=self._run_id,
        )

        parse_warnings: list[str] = []

        # Get or create domain profile
        profile = self._registry.get_or_default(source_config.url)

        try:
            # Transition to fetching
            state_machine.to_fetching()

            # Fetch the page
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
                self._metrics.record_parse_failure(domain)
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.FETCH,
                        message=str(result.error),
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            # Validate content-type
            content_type = result.headers.get("content-type", "")
            if not profile.is_content_type_allowed(content_type):
                log.warning(
                    "content_type_rejected",
                    content_type=content_type,
                )
                state_machine.to_failed()
                self._metrics.record_parse_failure(domain)
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.PARSE,
                        message=f"Content-Type not allowed: {content_type}",
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            # Handle 304 Not Modified
            if result.cache_hit:
                log.info("cache_hit_no_changes")
                state_machine.to_parsing_list()
                state_machine.to_done()
                return CollectorResult(
                    items=[],
                    state=SourceState.SOURCE_DONE,
                )

            # Transition to list parsing
            state_machine.to_parsing_list()

            # Parse the HTML
            soup = BeautifulSoup(result.body_bytes, "lxml")

            # Extract items from list
            items, links_found, links_filtered = self._parse_list_items(
                soup=soup,
                source_config=source_config,
                base_url=source_config.url,
                profile=profile,
                parse_warnings=parse_warnings,
            )

            # Record metrics for list parsing
            self._metrics.record_links_found(domain, links_found)
            self._metrics.record_links_filtered(domain, links_filtered)

            log.info(
                "list_parsing_complete",
                stage="list",
                links_found=links_found,
                links_filtered_out=links_filtered,
                items_extracted=len(items),
            )

            # Item page date recovery phase
            items = self._recover_item_dates(
                items=items,
                profile=profile,
                http_client=http_client,
                source_config=source_config,
                state_machine=state_machine,
                log=log,
            )

            # Filter by time: only keep items published in the last 24 hours
            items = self.filter_items_by_time(
                items=items,
                now=self._now,
                lookback_hours=self._lookback_hours,
                source_id=source_config.id,
            )

            # Sort deterministically
            items = self.sort_items_deterministically(items)

            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )

            # Enforce max_items
            items = self.enforce_max_items(items, max_items)

            duration_ms = (time.perf_counter_ns() - start_time) / 1_000_000

            log.info(
                "collection_complete",
                items_emitted=len(items),
                parse_warnings_count=len(parse_warnings),
                duration_ms=round(duration_ms, 2),
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
            self._metrics.record_parse_failure(domain)
            return CollectorResult(
                items=[],
                error=ErrorRecord.from_exception(e),
                parse_warnings=parse_warnings,
                state=SourceState.SOURCE_FAILED,
            )

        except Exception as e:  # noqa: BLE001
            log.warning("unexpected_error", error=str(e))
            state_machine.to_failed()
            self._metrics.record_parse_failure(domain)
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

    def _recover_item_dates(  # noqa: PLR0913
        self,
        items: list[Item],
        profile: DomainProfile,
        http_client: HttpFetcher,
        source_config: SourceConfig,
        state_machine: SourceStateMachine,
        log: structlog.typing.FilteringBoundLogger,
    ) -> list[Item]:
        """Recover dates from item pages for items with low date confidence.

        Args:
            items: Items to potentially recover dates for.
            profile: Domain profile with recovery settings.
            http_client: HTTP client for fetching.
            source_config: Source configuration.
            state_machine: State machine for tracking.
            log: Logger instance.

        Returns:
            Items with potentially recovered dates.
        """
        items_needing_recovery = sum(
            1
            for item in items
            if item.date_confidence == DateConfidence.LOW and item.published_at is None
        )

        if items_needing_recovery > 0 and profile.enable_item_page_recovery:
            state_machine.to_parsing_item_pages()

            item_fetcher = ItemPageFetcher(
                http_client=http_client,
                profile=profile,
                run_id=self._run_id,
            )

            items, recovery_report = item_fetcher.recover_dates_for_items(
                items=items,
                source_id=source_config.id,
            )

            log.info(
                "item_page_recovery_complete",
                stage="item",
                item_pages_fetched=recovery_report.pages_fetched,
                date_recovered_count=recovery_report.dates_recovered,
            )

        return items

    def _parse_list_items(  # noqa: PLR0912, PLR0915, C901
        self,
        soup: BeautifulSoup,
        source_config: SourceConfig,
        base_url: str,
        profile: DomainProfile,
        parse_warnings: list[str],
    ) -> tuple[list[Item], int, int]:
        """Parse list items from HTML.

        Args:
            soup: Parsed HTML.
            source_config: Source configuration.
            base_url: Base URL for resolving relative links.
            profile: Domain profile with extraction rules.
            parse_warnings: List to append warnings to.

        Returns:
            Tuple of (items list, links found, links filtered out).
        """
        items: list[Item] = []
        seen_urls: set[str] = set()
        links_found = 0
        links_filtered = 0

        # Create date extractor with profile rules
        date_extractor = DateExtractor(profile.date_rules, self._run_id)

        # Try to find article/item containers using profile rules
        raw_containers = soup.select(profile.link_rules.container_selector)
        containers: list[Tag] = [c for c in raw_containers if isinstance(c, Tag)]

        if not containers:
            # Fall back to common selectors
            containers = self._find_article_containers(soup)

        for container in containers:
            if not isinstance(container, Tag):
                continue

            try:
                links_found += 1

                # Find the main link using profile rules
                link_elem = container.select_one(profile.link_rules.link_selector)
                if not link_elem or not isinstance(link_elem, Tag):
                    links_filtered += 1
                    continue

                href = link_elem.get("href", "")
                if not href or isinstance(href, list):
                    links_filtered += 1
                    continue

                # Canonicalize URL
                canonical_url = self.canonicalize_url(str(href), base_url)

                # Validate URL
                if not self.validate_url(canonical_url):
                    links_filtered += 1
                    continue

                # Check filter patterns
                if self._matches_filter_pattern(
                    str(href), profile.link_rules.filter_patterns
                ):
                    links_filtered += 1
                    continue

                # Skip navigation links
                if self._is_navigation_link(link_elem, str(href)):
                    links_filtered += 1
                    continue

                # Skip duplicates
                if canonical_url in seen_urls:
                    links_filtered += 1
                    continue

                seen_urls.add(canonical_url)

                # Extract title using profile selectors
                title = self._extract_title(
                    container, link_elem, profile.link_rules.title_selectors
                )
                if not title:
                    title = f"Untitled from {source_config.name}"

                # Extract date using date extractor
                date_result = date_extractor.extract_from_html(soup, scope=container)

                # Build raw_json with required fields
                raw_data: dict[str, object] = {
                    "original_link": str(href),
                    "extracted_title": title,
                    "source_name": source_config.name,
                    "extraction_method": date_result.method.value,
                }

                if date_result.raw_date:
                    raw_data["extracted_date_raw"] = date_result.raw_date
                raw_data["candidate_dates"] = date_result.candidate_dates

                # Add description if available
                desc = self._extract_description(container)
                if desc:
                    raw_data["description"] = desc[:500]

                # Truncate raw_json if needed
                raw_json, _ = self.truncate_raw_json(raw_data)

                # Compute content hash
                content_hash = compute_content_hash(
                    title=title,
                    url=canonical_url,
                    published_at=date_result.published_at,
                )

                items.append(
                    Item(
                        url=canonical_url,
                        source_id=source_config.id,
                        tier=source_config.tier,
                        kind=source_config.kind.value,
                        title=title,
                        published_at=date_result.published_at,
                        date_confidence=date_result.confidence,
                        content_hash=content_hash,
                        raw_json=raw_json,
                    )
                )

            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to parse container: {e}")
                links_filtered += 1

        # If no containers found, fall back to extracting all links
        if not items:
            fallback_items, fb_found, fb_filtered = self._extract_all_links(
                soup=soup,
                source_config=source_config,
                base_url=base_url,
                profile=profile,
                parse_warnings=parse_warnings,
                seen_urls=seen_urls,
            )
            items = fallback_items
            links_found += fb_found
            links_filtered += fb_filtered

        return items, links_found, links_filtered

    def _find_article_containers(self, soup: BeautifulSoup) -> list[Tag]:
        """Find article/item containers in HTML.

        Args:
            soup: Parsed HTML.

        Returns:
            List of container elements.
        """
        # Try common article container patterns
        selectors = [
            "article",
            "[role='article']",
            ".post",
            ".article",
            ".blog-post",
            ".entry",
            ".news-item",
            ".card",
            "li.post",
            ".list-item",
        ]

        for selector in selectors:
            containers = soup.select(selector)
            if containers:
                return [c for c in containers if isinstance(c, Tag)]

        return []

    def _extract_title(
        self,
        container: Tag,
        link_elem: Tag,
        title_selectors: list[str],
    ) -> str:
        """Extract title from container.

        Args:
            container: Container element.
            link_elem: Link element.
            title_selectors: CSS selectors to try for title.

        Returns:
            Extracted title.
        """
        # Try heading elements from profile
        for selector in title_selectors:
            elem = container.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text:
                    return text

        # Try link text
        link_text = link_elem.get_text(strip=True)
        if link_text:
            return link_text

        # Try title attribute
        title_attr = link_elem.get("title", "")
        if title_attr and isinstance(title_attr, str):
            return title_attr

        return ""

    def _extract_description(self, container: Tag) -> str:
        """Extract description from container.

        Args:
            container: Container element.

        Returns:
            Description text.
        """
        # Try common description elements
        for selector in [".excerpt", ".summary", ".description", "p"]:
            elem = container.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > MIN_DESCRIPTION_LENGTH:
                    return text

        return ""

    def _extract_all_links(  # noqa: PLR0913
        self,
        soup: BeautifulSoup,
        source_config: SourceConfig,
        base_url: str,
        profile: DomainProfile,
        parse_warnings: list[str],
        seen_urls: set[str],
    ) -> tuple[list[Item], int, int]:
        """Extract items from all links as fallback.

        Args:
            soup: Parsed HTML.
            source_config: Source configuration.
            base_url: Base URL for resolving relative links.
            profile: Domain profile.
            parse_warnings: List to append warnings to.
            seen_urls: Set of already-seen URLs.

        Returns:
            Tuple of (items list, links found, links filtered).
        """
        items: list[Item] = []
        links_found = 0
        links_filtered = 0

        # Find main content area
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("[role='main']")
            or soup.find(class_="content")
            or soup.body
        )

        if not main_content:
            parse_warnings.append("Could not find main content area")
            return items, links_found, links_filtered

        if not isinstance(main_content, Tag):
            return items, links_found, links_filtered

        # Find all links in main content
        for link in main_content.find_all("a", href=True):
            if not isinstance(link, Tag):
                continue

            links_found += 1

            href = link.get("href", "")
            if not href or isinstance(href, list):
                links_filtered += 1
                continue

            # Skip navigation/footer links
            if self._is_navigation_link(link, str(href)):
                links_filtered += 1
                continue

            # Check filter patterns
            if self._matches_filter_pattern(
                str(href), profile.link_rules.filter_patterns
            ):
                links_filtered += 1
                continue

            # Canonicalize URL
            canonical_url = self.canonicalize_url(str(href), base_url)

            # Skip if already seen or invalid
            if canonical_url in seen_urls or not self.validate_url(canonical_url):
                links_filtered += 1
                continue

            # Get title from link text
            title = link.get_text(strip=True)
            if not title or len(title) < MIN_TITLE_LENGTH:
                links_filtered += 1
                continue

            seen_urls.add(canonical_url)

            # Build raw_json
            raw_data: dict[str, object] = {
                "original_link": str(href),
                "extracted_title": title,
                "source_name": source_config.name,
                "extraction_method": "link_fallback",
                "candidate_dates": [],
            }
            raw_json, _ = self.truncate_raw_json(raw_data)

            # Compute content hash
            content_hash = compute_content_hash(
                title=title,
                url=canonical_url,
            )

            items.append(
                Item(
                    url=canonical_url,
                    source_id=source_config.id,
                    tier=source_config.tier,
                    kind=source_config.kind.value,
                    title=title,
                    published_at=None,
                    date_confidence=DateConfidence.LOW,
                    content_hash=content_hash,
                    raw_json=raw_json,
                )
            )

        return items, links_found, links_filtered

    def _is_navigation_link(self, link: Tag, href: str) -> bool:
        """Check if link is likely a navigation link.

        Args:
            link: Link element.
            href: Link href.

        Returns:
            True if link appears to be navigation.
        """
        # Check href patterns
        nav_patterns = [
            r"^#",
            r"^javascript:",
            r"^mailto:",
            r"/page/\d+",
            r"\?page=",
            r"/category/",
            r"/tag/",
            r"/author/",
            r"/login",
            r"/signup",
            r"/contact",
            r"/about",
            r"/privacy",
            r"/terms",
        ]

        for pattern in nav_patterns:
            if re.search(pattern, href, re.IGNORECASE):
                return True

        # Check if in nav/header/footer
        for parent in link.parents:
            if parent.name in ("nav", "header", "footer", "aside"):
                return True
            parent_class = parent.get("class")
            if isinstance(parent_class, list):
                class_str = " ".join(parent_class).lower()
                if any(
                    nav in class_str
                    for nav in ["nav", "menu", "sidebar", "footer", "header"]
                ):
                    return True

        return False

    def _matches_filter_pattern(self, url: str, patterns: list[str]) -> bool:
        """Check if URL matches any filter pattern.

        Args:
            url: URL to check.
            patterns: Regex patterns to match.

        Returns:
            True if URL matches any pattern.
        """
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)
