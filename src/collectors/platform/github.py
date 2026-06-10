"""GitHub releases collector.

This module provides a collector for GitHub repository releases,
capturing release tags, publication dates, and release notes.
"""

import json
import re
import time
from datetime import datetime
from typing import Any

import structlog

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.errors import CollectorErrorClass, ErrorRecord
from src.collectors.platform.constants import (
    AUTH_ERROR_HINTS,
    FIELD_PLATFORM,
    FIELD_PRERELEASE,
    FIELD_RELEASE_ID,
    FIELD_RELEASE_NOTES_URL,
    FIELD_TAG_NAME,
    GITHUB_API_BASE_URL,
    GITHUB_API_RELEASES_PATH,
    GITHUB_AUTHENTICATED_MAX_QPS,
    GITHUB_DEFAULT_MAX_QPS,
    PLATFORM_GITHUB,
    RELEASE_BODY_MAX_LENGTH,
)
from src.collectors.platform.helpers import get_auth_token, is_auth_error, truncate_text
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

# Regex to extract owner/repo from GitHub URL
GITHUB_REPO_PATTERN = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)")


def extract_owner_repo(url: str) -> tuple[str, str] | None:
    """Extract owner and repo from a GitHub URL.

    Args:
        url: GitHub repository URL.

    Returns:
        Tuple of (owner, repo) or None if not a valid GitHub URL.
    """
    match = GITHUB_REPO_PATTERN.search(url)
    if match:
        return match.group("owner"), match.group("repo")
    return None


class GitHubReleasesCollector(BaseCollector):
    """Collector for GitHub repository releases.

    Monitors configured repos and ingests:
    - Release tag
    - published_at timestamp
    - Prerelease flag
    - Release notes URL

    Canonical URL is the release HTML URL.

    API documentation: https://docs.github.com/en/rest/releases
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        """Initialize the GitHub releases collector.

        Args:
            strip_params: URL parameters to strip (not used for GitHub).
            run_id: Run identifier for logging.
            rate_limiter: Optional rate limiter for dependency injection.
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._metrics = PlatformMetrics.get_instance()

        # Determine rate limit based on whether we have a token
        has_token = bool(get_auth_token(PLATFORM_GITHUB))
        max_qps = GITHUB_AUTHENTICATED_MAX_QPS if has_token else GITHUB_DEFAULT_MAX_QPS
        self._rate_limiter = rate_limiter or get_platform_rate_limiter(
            PLATFORM_GITHUB, max_qps
        )

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect releases from a GitHub repository.

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
            platform=PLATFORM_GITHUB,
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

            # Extract owner/repo from URL
            owner_repo = extract_owner_repo(source_config.url)
            if not owner_repo:
                log.warning("invalid_github_url", url=source_config.url)
                state_machine.to_failed()
                return CollectorResult(
                    items=[],
                    error=ErrorRecord(
                        error_class=CollectorErrorClass.SCHEMA,
                        message=f"Invalid GitHub repository URL: {source_config.url}",
                        source_id=source_config.id,
                    ),
                    state=SourceState.SOURCE_FAILED,
                )

            owner, repo = owner_repo
            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )
            api_url = self._build_api_url(
                owner,
                repo,
                self.resolve_fetch_limit(
                    max_items=max_items, fallback_limit=100, api_cap=100
                ),
            )

            log.info(
                "fetching_releases",
                owner=owner,
                repo=repo,
            )

            # Acquire rate limit token
            self._rate_limiter.acquire()

            # Build headers with auth if available
            headers = self._build_headers()

            # Fetch releases
            start_time = time.monotonic()
            result = http_client.fetch(
                source_id=source_config.id,
                url=api_url,
                extra_headers=headers,
            )
            duration_ms = (time.monotonic() - start_time) * 1000
            self._metrics.record_api_call(PLATFORM_GITHUB)

            # Check for auth errors
            if result.error:
                if is_auth_error(result):
                    remediation = AUTH_ERROR_HINTS[PLATFORM_GITHUB]
                    log.warning(
                        "auth_error",
                        status_code=result.status_code,
                        remediation=remediation,
                    )
                    self._metrics.record_error(PLATFORM_GITHUB, "auth")
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
                self._metrics.record_error(PLATFORM_GITHUB, "fetch")
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
            items = self._parse_releases(
                body=result.body_bytes,
                source_config=source_config,
                owner=owner,
                repo=repo,
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

            self._metrics.record_items(PLATFORM_GITHUB, len(items))

            # Check if we were rate limited
            rate_limited = self._rate_limiter.was_rate_limited

            log.info(
                "collection_complete",
                items_emitted=len(items),
                org=owner,
                repo=repo,
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
            self._metrics.record_error(PLATFORM_GITHUB, "parse")
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

    def _build_api_url(self, owner: str, repo: str, per_page: int) -> str:
        """Build GitHub API URL for releases.

        Args:
            owner: Repository owner.
            repo: Repository name.
            per_page: Number of releases to fetch.

        Returns:
            Full API URL.
        """
        path = GITHUB_API_RELEASES_PATH.format(owner=owner, repo=repo)
        # Cap per_page to GitHub's max of 100
        per_page = min(per_page, 100)
        return f"{GITHUB_API_BASE_URL}{path}?per_page={per_page}"

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with optional auth.

        Returns:
            Headers dictionary.
        """
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        token = get_auth_token(PLATFORM_GITHUB)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return headers

    def _parse_releases(
        self,
        body: bytes,
        source_config: SourceConfig,
        owner: str,
        repo: str,
        parse_warnings: list[str],
    ) -> list[Item]:
        """Parse GitHub releases JSON response.

        Args:
            body: Response body bytes.
            source_config: Source configuration.
            owner: Repository owner.
            repo: Repository name.
            parse_warnings: List to append warnings to.

        Returns:
            List of parsed items.
        """
        items: list[Item] = []

        try:
            releases = json.loads(body)
        except json.JSONDecodeError as e:
            parse_warnings.append(f"Failed to parse JSON response: {e}")
            return []

        if not isinstance(releases, list):
            parse_warnings.append("Expected array of releases")
            return []

        for release in releases:
            try:
                item = self._parse_release(release, source_config, owner, repo)
                if item:
                    items.append(item)
            except Exception as e:  # noqa: BLE001
                parse_warnings.append(f"Failed to parse release: {e}")

        return items

    def _parse_release(
        self,
        release: dict[str, Any],
        source_config: SourceConfig,
        owner: str,
        repo: str,
    ) -> Item | None:
        """Parse a single release object.

        Args:
            release: Release JSON object.
            source_config: Source configuration.
            owner: Repository owner.
            repo: Repository name.

        Returns:
            Item if parsing succeeded, None otherwise.
        """
        # Extract required fields
        release_id = release.get("id")
        html_url = release.get("html_url")
        tag_name = release.get("tag_name")
        name = release.get("name") or tag_name or f"Release {release_id}"

        if not html_url:
            return None

        # Extract dates
        published_at = None
        date_confidence = DateConfidence.LOW

        published_at_str = release.get("published_at")
        if published_at_str:
            try:
                published_at = datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )
                date_confidence = DateConfidence.HIGH
            except ValueError:
                pass

        # Build raw_json
        raw_data = self._build_raw_data(release, owner, repo)
        raw_json, _ = self.truncate_raw_json(raw_data)

        # Compute content hash
        content_hash = self._compute_content_hash(release, html_url)

        return Item(
            url=html_url,
            source_id=source_config.id,
            tier=source_config.tier,
            kind=source_config.kind.value,
            title=name,
            published_at=published_at,
            date_confidence=date_confidence,
            content_hash=content_hash,
            raw_json=raw_json,
        )

    def _build_raw_data(
        self,
        release: dict[str, Any],
        owner: str,
        repo: str,
    ) -> dict[str, Any]:
        """Build raw_json data from release.

        Args:
            release: Release JSON object.
            owner: Repository owner.
            repo: Repository name.

        Returns:
            Dictionary of raw metadata.
        """
        raw_data: dict[str, Any] = {
            FIELD_PLATFORM: PLATFORM_GITHUB,
            "owner": owner,
            "repo": repo,
        }

        if release.get("id"):
            raw_data[FIELD_RELEASE_ID] = release["id"]

        if release.get("tag_name"):
            raw_data[FIELD_TAG_NAME] = release["tag_name"]

        if release.get("prerelease") is not None:
            raw_data[FIELD_PRERELEASE] = release["prerelease"]

        if release.get("html_url"):
            raw_data[FIELD_RELEASE_NOTES_URL] = release["html_url"]

        if release.get("name"):
            raw_data["name"] = release["name"]

        if release.get("published_at"):
            raw_data["published_at"] = release["published_at"]

        if release.get("created_at"):
            raw_data["created_at"] = release["created_at"]

        # Truncate body if present using helper
        if release.get("body"):
            raw_data["body"] = truncate_text(release["body"], RELEASE_BODY_MAX_LENGTH)

        return raw_data

    def _compute_content_hash(
        self,
        release: dict[str, Any],
        html_url: str,
    ) -> str:
        """Compute content hash for release.

        Hash is computed from: name, tag_name, body (release notes).

        Args:
            release: Release JSON object.
            html_url: Canonical URL.

        Returns:
            Content hash string.
        """
        name = release.get("name") or release.get("tag_name") or ""
        tag = release.get("tag_name") or ""

        extra: dict[str, str] = {}
        if tag:
            extra["tag_name"] = tag

        body = release.get("body")
        if body:
            # Use first 500 chars of body for hash
            extra["body_snippet"] = body[:500]

        updated_at = release.get("published_at") or release.get("created_at")
        if updated_at:
            extra["updated_at"] = updated_at

        return compute_content_hash(
            title=name,
            url=html_url,
            extra=extra if extra else None,
        )
