"""Date extraction with precedence-based strategies."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from re import Pattern

import structlog
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from src.collectors.html_profile.models import DateExtractionMethod, DateExtractionRule
from src.collectors.html_profile.utils import RegexCache
from src.features.store.models import DateConfidence


logger = structlog.get_logger()


@dataclass
class DateExtractionResult:
    """Result of date extraction.

    Attributes:
        published_at: Extracted datetime, or None if not found.
        confidence: Confidence level for the extracted date.
        method: Method used to extract the date.
        raw_date: The raw date string that was parsed.
        candidate_dates: List of all candidate dates found.
    """

    published_at: datetime | None
    confidence: DateConfidence
    method: DateExtractionMethod
    raw_date: str | None = None
    candidate_dates: list[dict[str, str]] = field(default_factory=list)


class DateExtractor:
    """Extracts dates from HTML using configurable precedence-based strategies.

    Strategy order (highest to lowest precedence):
    1. <time datetime="..."> element
    2. <meta property="article:published_time"> tag
    3. JSON-LD Article.datePublished
    4. Regex text patterns
    """

    def __init__(
        self,
        rules: DateExtractionRule | None = None,
        run_id: str = "",
    ) -> None:
        """Initialize the date extractor.

        Args:
            rules: Extraction rules to use.
            run_id: Run identifier for logging.
        """
        self._rules = rules or DateExtractionRule()
        self._run_id = run_id
        self._log = logger.bind(component="date_extractor", run_id=run_id)
        # Pre-compile regex patterns for better performance
        self._regex_cache = RegexCache()
        self._compiled_patterns: list[Pattern[str]] = self._regex_cache.compile_all(
            self._rules.text_patterns
        )

    def extract_from_html(
        self,
        html: str | BeautifulSoup,
        scope: Tag | None = None,
    ) -> DateExtractionResult:
        """Extract date from HTML content.

        Args:
            html: HTML content or BeautifulSoup object.
            scope: Optional element to limit extraction scope.

        Returns:
            DateExtractionResult with extracted date and metadata.
        """
        soup = BeautifulSoup(html, "lxml") if isinstance(html, str) else html
        search_scope: Tag | BeautifulSoup = scope if scope is not None else soup
        candidate_dates: list[dict[str, str]] = []

        # Strategy 1: <time datetime>
        result = self._try_time_element(search_scope, candidate_dates)
        if result.published_at:
            return result

        # Strategy 2: Meta tags
        result = self._try_meta_tags(soup, candidate_dates)
        if result.published_at:
            return result

        # Strategy 3: JSON-LD
        result = self._try_json_ld(soup, candidate_dates)
        if result.published_at:
            return result

        # Strategy 4: Text patterns
        result = self._try_text_patterns(search_scope, candidate_dates)
        if result.published_at:
            return result

        # No date found
        return DateExtractionResult(
            published_at=None,
            confidence=DateConfidence.LOW,
            method=DateExtractionMethod.NONE,
            raw_date=None,
            candidate_dates=candidate_dates,
        )

    def _try_time_element(
        self,
        scope: Tag | BeautifulSoup,
        candidates: list[dict[str, str]],
    ) -> DateExtractionResult:
        """Try extracting date from <time datetime> element.

        Args:
            scope: Element to search within.
            candidates: List to append candidates to.

        Returns:
            DateExtractionResult.
        """
        time_elems = scope.select(self._rules.time_selector)

        for elem in time_elems:
            if not isinstance(elem, Tag):
                continue

            dt_str = elem.get("datetime")
            if not dt_str or isinstance(dt_str, list):
                continue

            dt_str = str(dt_str)
            candidates.append(
                {
                    "source": "time_element",
                    "raw": dt_str,
                    "selector": self._rules.time_selector,
                }
            )

            parsed = self._parse_date_string(dt_str)
            if parsed:
                self._log.debug(
                    "date_extracted",
                    method="time_element",
                    raw=dt_str,
                )
                return DateExtractionResult(
                    published_at=parsed,
                    confidence=DateConfidence.HIGH,
                    method=DateExtractionMethod.TIME_ELEMENT,
                    raw_date=dt_str,
                    candidate_dates=candidates,
                )

        return DateExtractionResult(
            published_at=None,
            confidence=DateConfidence.LOW,
            method=DateExtractionMethod.NONE,
            candidate_dates=candidates,
        )

    def _try_meta_tags(
        self,
        soup: BeautifulSoup,
        candidates: list[dict[str, str]],
    ) -> DateExtractionResult:
        """Try extracting date from meta tags.

        Args:
            soup: BeautifulSoup object to search.
            candidates: List to append candidates to.

        Returns:
            DateExtractionResult.
        """
        for prop in self._rules.meta_properties:
            # Try property attribute
            meta = soup.find("meta", property=prop)
            if meta and isinstance(meta, Tag):
                content = meta.get("content")
                if content and isinstance(content, str):
                    candidates.append(
                        {
                            "source": "meta_tag",
                            "property": prop,
                            "raw": content,
                        }
                    )

                    parsed = self._parse_date_string(content)
                    if parsed:
                        self._log.debug(
                            "date_extracted",
                            method="meta_published_time",
                            property=prop,
                            raw=content,
                        )
                        return DateExtractionResult(
                            published_at=parsed,
                            confidence=DateConfidence.HIGH,
                            method=DateExtractionMethod.META_PUBLISHED_TIME,
                            raw_date=content,
                            candidate_dates=candidates,
                        )

            # Try itemprop attribute
            meta = soup.find("meta", itemprop=prop)
            if meta and isinstance(meta, Tag):
                content = meta.get("content")
                if content and isinstance(content, str):
                    candidates.append(
                        {
                            "source": "meta_itemprop",
                            "itemprop": prop,
                            "raw": content,
                        }
                    )

                    parsed = self._parse_date_string(content)
                    if parsed:
                        self._log.debug(
                            "date_extracted",
                            method="meta_published_time",
                            itemprop=prop,
                            raw=content,
                        )
                        return DateExtractionResult(
                            published_at=parsed,
                            confidence=DateConfidence.HIGH,
                            method=DateExtractionMethod.META_PUBLISHED_TIME,
                            raw_date=content,
                            candidate_dates=candidates,
                        )

        return DateExtractionResult(
            published_at=None,
            confidence=DateConfidence.LOW,
            method=DateExtractionMethod.NONE,
            candidate_dates=candidates,
        )

    def _try_json_ld(
        self,
        soup: BeautifulSoup,
        candidates: list[dict[str, str]],
    ) -> DateExtractionResult:
        """Try extracting date from JSON-LD.

        Args:
            soup: BeautifulSoup object to search.
            candidates: List to append candidates to.

        Returns:
            DateExtractionResult.
        """
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                content = script.string
                if not content:
                    continue

                data = json.loads(content)

                # Handle array of objects
                if isinstance(data, list):
                    for item in data:
                        result = self._extract_date_from_json_ld_object(
                            item, candidates
                        )
                        if result.published_at:
                            return result
                elif isinstance(data, dict):
                    result = self._extract_date_from_json_ld_object(data, candidates)
                    if result.published_at:
                        return result

            except (json.JSONDecodeError, TypeError):
                continue

        return DateExtractionResult(
            published_at=None,
            confidence=DateConfidence.LOW,
            method=DateExtractionMethod.NONE,
            candidate_dates=candidates,
        )

    def _extract_date_from_json_ld_object(
        self,
        data: dict[str, object],
        candidates: list[dict[str, str]],
    ) -> DateExtractionResult:
        """Extract date from a JSON-LD object.

        Args:
            data: JSON-LD object.
            candidates: List to append candidates to.

        Returns:
            DateExtractionResult.
        """
        # Check for article types
        ld_type = data.get("@type", "")
        if isinstance(ld_type, list):
            ld_type = ld_type[0] if ld_type else ""

        # Try date keys in order
        for key in self._rules.json_ld_keys:
            if key in data:
                value = data[key]
                if not isinstance(value, str):
                    continue

                candidates.append(
                    {
                        "source": "json_ld",
                        "key": key,
                        "@type": str(ld_type),
                        "raw": value,
                    }
                )

                parsed = self._parse_date_string(value)
                if parsed:
                    # datePublished gets HIGH confidence, others get MEDIUM
                    confidence = (
                        DateConfidence.HIGH
                        if key == "datePublished"
                        else DateConfidence.MEDIUM
                    )

                    self._log.debug(
                        "date_extracted",
                        method="json_ld",
                        key=key,
                        raw=value,
                    )

                    return DateExtractionResult(
                        published_at=parsed,
                        confidence=confidence,
                        method=DateExtractionMethod.JSON_LD,
                        raw_date=value,
                        candidate_dates=candidates,
                    )

        return DateExtractionResult(
            published_at=None,
            confidence=DateConfidence.LOW,
            method=DateExtractionMethod.NONE,
            candidate_dates=candidates,
        )

    def _try_text_patterns(
        self,
        scope: Tag | BeautifulSoup,
        candidates: list[dict[str, str]],
    ) -> DateExtractionResult:
        """Try extracting date using regex patterns in text.

        Uses pre-compiled regex patterns for better performance.

        Args:
            scope: Element to search within.
            candidates: List to append candidates to.

        Returns:
            DateExtractionResult.
        """
        text = scope.get_text(separator=" ", strip=True)

        # Use pre-compiled patterns for better performance
        for compiled_pattern in self._compiled_patterns:
            matches = compiled_pattern.findall(text)
            for match in matches:
                candidates.append(
                    {
                        "source": "text_pattern",
                        "pattern": compiled_pattern.pattern,
                        "raw": match,
                    }
                )

                parsed = self._parse_date_string(match)
                if parsed:
                    self._log.debug(
                        "date_extracted",
                        method="text_pattern",
                        pattern=compiled_pattern.pattern,
                        raw=match,
                    )
                    return DateExtractionResult(
                        published_at=parsed,
                        confidence=DateConfidence.MEDIUM,
                        method=DateExtractionMethod.TEXT_PATTERN,
                        raw_date=match,
                        candidate_dates=candidates,
                    )

        return DateExtractionResult(
            published_at=None,
            confidence=DateConfidence.LOW,
            method=DateExtractionMethod.NONE,
            candidate_dates=candidates,
        )

    def _parse_date_string(self, date_str: str) -> datetime | None:
        """Parse a date string into datetime.

        Args:
            date_str: Date string to parse.

        Returns:
            Parsed datetime or None.
        """
        try:
            dt = date_parser.parse(date_str)
            # Ensure timezone aware
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        except (ValueError, TypeError, OverflowError):
            return None
