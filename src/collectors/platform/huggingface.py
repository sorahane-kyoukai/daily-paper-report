"""Hugging Face org models collector.

This module provides a collector for Hugging Face organization models,
capturing model IDs, last modified timestamps, and metadata.
"""

import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import structlog

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import CollectorErrorClass, ErrorRecord
from src.collectors.platform.constants import (
    AUTH_ERROR_HINTS,
    FIELD_LAST_MODIFIED,
    FIELD_LICENSE,
    FIELD_MODEL_CARD_URL,
    FIELD_MODEL_ID,
    FIELD_PIPELINE_TAG,
    FIELD_PLATFORM,
    FIELD_README_SUMMARY,
    HF_API_BASE_URL,
    HF_API_MODELS_PATH,
    HF_DEFAULT_MAX_QPS,
    PLATFORM_HUGGINGFACE,
    README_MIN_LINE_LENGTH,
    README_SUMMARY_MAX_LENGTH,
)
from src.collectors.platform.helpers import get_auth_token, is_auth_error
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

# Regex to extract org from HuggingFace URL
HF_ORG_PATTERN = re.compile(r"huggingface\.co/(?P<org>[^/]+)/?$")


def extract_org(url: str) -> str | None:
    """Extract organization from a HuggingFace URL.

    Args:
        url: HuggingFace organization URL.

    Returns:
        Organization name or None if not a valid HuggingFace org URL.
    """
    match = HF_ORG_PATTERN.search(url)
    if match:
        return match.group("org")
    return None


class HuggingFaceOrgCollector(BaseCollector):
    """Collector for Hugging Face organization models.

    Lists models for configured orgs and ingests:
    - model_id
    - lastModified timestamp
    - pipeline_tag
    - license
    - model card URL

    Canonical URL is the model page URL.

    API documentation: https://huggingface.co/docs/hub/api
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        """Initialize the HuggingFace org collector.

        Args:
            strip_params: URL parameters to strip (not used for HuggingFace).
            run_id: Run identifier for logging.
            rate_limiter: Optional rate limiter for dependency injection.
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._metrics = PlatformMetrics.get_instance()
        self._rate_limiter = rate_limiter or get_platform_rate_limiter(
            PLATFORM_HUGGINGFACE, HF_DEFAULT_MAX_QPS
        )

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect models from a HuggingFace organization.

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
            platform=PLATFORM_HUGGINGFACE,
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

            # Extract org from URL
            org = extract_org(source_config.url)
            if not org:
                log.warning("invalid_hf_url", url=source_config.url)
                state_machine.to_failed()
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.SCHEMA,
                        message=f"Invalid HuggingFace organization URL: {source_config.url}",
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )
            api_url = self._build_api_url(
                org,
                self.resolve_fetch_limit(
                    max_items=max_items, fallback_limit=100, api_cap=1000
                ),
            )

            log.info(
                "fetching_models",
                org=org,
            )

            # Acquire rate limit token
            self._rate_limiter.acquire()

            # Build headers with auth if available
            headers = self._build_headers()

            # Fetch models
            start_time = time.monotonic()
            result = http_client.fetch(
                source_id=source_config.id,
                url=api_url,
                extra_headers=headers,
            )
            duration_ms = (time.monotonic() - start_time) * 1000
            self._metrics.record_api_call(PLATFORM_HUGGINGFACE)

            # Check for auth errors
            if result.error:
                if is_auth_error(result):
                    remediation = AUTH_ERROR_HINTS[PLATFORM_HUGGINGFACE]
                    log.warning(
                        "auth_error",
                        status_code=result.status_code,
                        remediation=remediation,
                    )
                    self._metrics.record_error(PLATFORM_HUGGINGFACE, "auth")
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
                self._metrics.record_error(PLATFORM_HUGGINGFACE, "fetch")
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
            items = self._parse_models(
                body=result.body_bytes,
                source_config=source_config,
                org=org,
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

            # Fetch README summaries for each model
            items = self._enrich_with_readme_summaries(
                items=items,
                http_client=http_client,
                source_id=source_config.id,
                parse_warnings=parse_warnings,
                log=log,
            )

            self._metrics.record_items(PLATFORM_HUGGINGFACE, len(items))

            # Check if we were rate limited
            rate_limited = self._rate_limiter.was_rate_limited

            log.info(
                "collection_complete",
                items_emitted=len(items),
                org=org,
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
            self._metrics.record_error(PLATFORM_HUGGINGFACE, "parse")
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

    def _build_api_url(self, org: str, limit: int) -> str:
        """Build HuggingFace API URL for models.

        Args:
            org: Organization name.
            limit: Number of models to fetch.

        Returns:
            Full API URL.
        """
        params = {
            "author": org,
            "limit": min(limit, 1000),  # HF API limit
            "sort": "lastModified",
            "direction": "-1",  # Descending
        }
        return f"{HF_API_BASE_URL}{HF_API_MODELS_PATH}?{urlencode(params)}"

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with optional auth.

        Returns:
            Headers dictionary.
        """
        headers: dict[str, str] = {
            "Accept": "application/json",
        }

        token = get_auth_token(PLATFORM_HUGGINGFACE)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return headers

    def _parse_models(
        self,
        body: bytes,
        source_config: SourceConfig,
        org: str,  # noqa: ARG002
        parse_warnings: list[str],
    ) -> list[Item]:
        """Parse HuggingFace models JSON response.

        Args:
            body: Response body bytes.
            source_config: Source configuration.
            org: Organization name (unused, models contain full ID).
            parse_warnings: List to append warnings to.

        Returns:
            List of parsed items.
        """
        items: list[Item] = []

        try:
            models = json.loads(body)
        except json.JSONDecodeError as e:
            parse_warnings.append(f"Failed to parse JSON response: {e}")
            return []

        if not isinstance(models, list):
            parse_warnings.append("Expected array of models")
            return []

        for model in models:
            try:
                item = self._parse_model(model, source_config)
                if item:
                    items.append(item)
            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to parse model: {e}")

        return items

    def _parse_model(
        self,
        model: dict[str, Any],
        source_config: SourceConfig,
    ) -> Item | None:
        """Parse a single model object.

        Args:
            model: Model JSON object.
            source_config: Source configuration.

        Returns:
            Item if parsing succeeded, None otherwise.
        """
        # Extract required fields
        model_id = model.get("id") or model.get("modelId")
        if not model_id:
            return None

        # Build canonical URL
        canonical_url = f"https://huggingface.co/{model_id}"

        # Use model_id as title
        title = model_id

        # Extract dates
        published_at = None
        date_confidence = DateConfidence.LOW

        last_modified = model.get("lastModified")
        if last_modified:
            try:
                published_at = datetime.fromisoformat(
                    last_modified.replace("Z", "+00:00")
                )
                date_confidence = DateConfidence.HIGH
            except ValueError:
                pass

        # Build raw_json
        raw_data = self._build_raw_data(model)
        raw_json, _ = self.truncate_raw_json(raw_data)

        # Compute content hash
        content_hash = self._compute_content_hash(model, canonical_url)

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
        model: dict[str, Any],
    ) -> dict[str, Any]:
        """Build raw_json data from model.

        Args:
            model: Model JSON object.

        Returns:
            Dictionary of raw metadata.
        """
        raw_data: dict[str, Any] = {
            FIELD_PLATFORM: PLATFORM_HUGGINGFACE,
        }

        model_id = model.get("id") or model.get("modelId")
        if model_id:
            raw_data[FIELD_MODEL_ID] = model_id

        if model.get("lastModified"):
            raw_data[FIELD_LAST_MODIFIED] = model["lastModified"]

        if model.get("pipeline_tag"):
            raw_data[FIELD_PIPELINE_TAG] = model["pipeline_tag"]

        # License can be in different places
        card_data = model.get("cardData") or {}
        license_value = model.get("license") or card_data.get("license")
        if license_value:
            raw_data[FIELD_LICENSE] = license_value

        # Model card URL
        if model_id:
            raw_data[FIELD_MODEL_CARD_URL] = f"https://huggingface.co/{model_id}"

        # Include author if present
        if model.get("author"):
            raw_data["author"] = model["author"]

        # Include downloads if present
        if model.get("downloads") is not None:
            raw_data["downloads"] = model["downloads"]

        # Include likes if present
        if model.get("likes") is not None:
            raw_data["likes"] = model["likes"]

        return raw_data

    def _compute_content_hash(
        self,
        model: dict[str, Any],
        canonical_url: str,
    ) -> str:
        """Compute content hash for model.

        Hash is computed from: model_id, lastModified, pipeline_tag.

        Args:
            model: Model JSON object.
            canonical_url: Canonical URL.

        Returns:
            Content hash string.
        """
        model_id = model.get("id") or model.get("modelId") or ""

        extra: dict[str, str] = {}

        if model.get("lastModified"):
            extra["lastModified"] = model["lastModified"]

        if model.get("pipeline_tag"):
            extra["pipeline_tag"] = model["pipeline_tag"]

        return compute_content_hash(
            title=model_id,
            url=canonical_url,
            extra=extra if extra else None,
        )

    def _fetch_readme_summary(
        self,
        model_id: str,
        http_client: HttpFetcher,
        source_id: str,
    ) -> str | None:
        """Fetch and extract summary from model's README.md.

        Args:
            model_id: HuggingFace model ID (e.g., 'openai/whisper-large-v3').
            http_client: HTTP client for fetching.
            source_id: Source ID for logging.

        Returns:
            Summary string extracted from README or None if unavailable.
        """
        readme_url = f"https://huggingface.co/{model_id}/raw/main/README.md"

        # Rate limit
        self._rate_limiter.acquire()

        result = http_client.fetch(
            source_id=source_id,
            url=readme_url,
            extra_headers=self._build_headers(),
        )

        if result.error or not result.body_bytes:
            return None

        try:
            readme_text = result.body_bytes.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return None

        return self._extract_readme_summary(readme_text)

    def _extract_readme_summary(self, readme_text: str) -> str | None:
        """Extract summary from README markdown content.

        Removes YAML frontmatter, markdown headers, HTML tags, and badges to find
        the first meaningful paragraph of text.

        Args:
            readme_text: Raw README.md content.

        Returns:
            Extracted summary or None if no meaningful content found.
        """
        # Remove YAML frontmatter (---...---)
        readme_text = re.sub(r"^---\n.*?\n---\n", "", readme_text, flags=re.DOTALL)

        # Remove HTML tags entirely
        readme_text = re.sub(r"<[^>]+>", "", readme_text)

        # Remove markdown links but keep text: [text](url) -> text
        readme_text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", readme_text)

        # Remove markdown images: ![alt](url)
        readme_text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", readme_text)

        # Split into lines and filter
        lines = readme_text.split("\n")
        content_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Skip empty lines
            if not stripped:
                continue
            # Skip markdown headers
            if stripped.startswith("#"):
                continue
            # Skip badge-style markdown: [!badge]
            if stripped.startswith("[!"):
                continue
            # Skip HTML comments
            if stripped.startswith("<!--"):
                continue
            # Skip horizontal rules
            if stripped in ("---", "***", "___"):
                continue
            # Skip lines that are too short (likely just whitespace/separators)
            if len(stripped) < README_MIN_LINE_LENGTH:
                continue
            content_lines.append(stripped)

        # Join first 10 non-empty lines
        summary = " ".join(content_lines[:10])

        # Clean up extra whitespace
        summary = re.sub(r"\s+", " ", summary).strip()

        if not summary:
            return None

        # Truncate to max length, breaking at word boundary
        if len(summary) > README_SUMMARY_MAX_LENGTH:
            summary = summary[:README_SUMMARY_MAX_LENGTH].rsplit(" ", 1)[0] + "..."

        return summary

    def _enrich_with_readme_summaries(
        self,
        items: list[Item],
        http_client: HttpFetcher,
        source_id: str,
        parse_warnings: list[str],
        log: structlog.stdlib.BoundLogger,
    ) -> list[Item]:
        """Enrich items with README summaries.

        Fetches README.md for each model and extracts a summary to store
        in the raw_json field.

        Args:
            items: List of items to enrich.
            http_client: HTTP client for fetching.
            source_id: Source ID for logging.
            parse_warnings: List to append warnings to.
            log: Logger instance.

        Returns:
            List of enriched items.
        """
        enriched_items: list[Item] = []

        for item in items:
            try:
                raw_data = json.loads(item.raw_json) if item.raw_json else {}
                model_id = raw_data.get(FIELD_MODEL_ID)

                if model_id:
                    log.debug("fetching_readme", model_id=model_id)
                    readme_summary = self._fetch_readme_summary(
                        model_id=model_id,
                        http_client=http_client,
                        source_id=source_id,
                    )

                    if readme_summary:
                        raw_data[FIELD_README_SUMMARY] = readme_summary
                        new_raw_json, _ = self.truncate_raw_json(raw_data)
                        # Create new Item with updated raw_json
                        enriched_item = Item(
                            url=item.url,
                            source_id=item.source_id,
                            tier=item.tier,
                            kind=item.kind,
                            title=item.title,
                            published_at=item.published_at,
                            date_confidence=item.date_confidence,
                            content_hash=item.content_hash,
                            raw_json=new_raw_json,
                            first_seen_at=item.first_seen_at,
                        )
                        enriched_items.append(enriched_item)
                        continue

                enriched_items.append(item)
            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to fetch README for item: {e}")
                enriched_items.append(item)

        return enriched_items
