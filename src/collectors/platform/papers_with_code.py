"""Papers With Code collector for quality signal papers."""

import json
from datetime import datetime
from typing import Any

import structlog

from src.collectors.arxiv.utils import extract_arxiv_id as _extract_arxiv_id
from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.platform.constants import (
    PAPERS_WITH_CODE_API_BASE_URL,
    PAPERS_WITH_CODE_DEFAULT_MAX_QPS,
    PAPERS_WITH_CODE_PAPERS_PATH,
    PLATFORM_PAPERS_WITH_CODE,
)
from src.collectors.platform.metrics import PlatformMetrics
from src.collectors.platform.rate_limiter import (
    TokenBucketRateLimiter,
    get_platform_rate_limiter,
)
from src.collectors.state_machine import SourceStateMachine
from src.features.config.schemas.sources import SourceConfig
from src.features.fetch.client import HttpFetcher
from src.features.store.hash import compute_content_hash
from src.features.store.models import DateConfidence, Item


logger = structlog.get_logger()


def extract_arxiv_id(url: str | None, arxiv_url: str | None) -> str | None:
    """Extract arXiv ID from paper URL or dedicated arxiv_url field.

    Delegates to central arXiv utility for comprehensive ID extraction.

    Args:
        url: Paper URL.
        arxiv_url: Dedicated arXiv URL if available.

    Returns:
        arXiv ID or None.
    """
    for source in [arxiv_url, url]:
        if source:
            arxiv_id = _extract_arxiv_id(source)
            if arxiv_id:
                return arxiv_id
    return None


class PapersWithCodeCollector(BaseCollector):
    """Collector for Papers With Code trending papers.

    Fetches recent papers from Papers With Code API to identify
    quality papers with code implementations.
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        """Initialize the Papers With Code collector.

        Args:
            strip_params: URL parameters to strip for canonicalization.
            run_id: Run identifier for logging.
            rate_limiter: Rate limiter for API throttling.
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._metrics = PlatformMetrics.get_instance()
        self._rate_limiter = rate_limiter or get_platform_rate_limiter(
            platform=PLATFORM_PAPERS_WITH_CODE,
            max_qps=PAPERS_WITH_CODE_DEFAULT_MAX_QPS,
        )
        self._log = logger.bind(
            component="collector",
            subcomponent="papers_with_code",
            run_id=run_id,
        )

    def collect(
        self,
        source_config: SourceConfig,
        http_client: HttpFetcher,
        now: datetime,
        lookback_hours: int = 24,
        max_items_override: int | None = None,
    ) -> CollectorResult:
        """Collect papers from Papers With Code API.

        Args:
            source_config: Source configuration.
            http_client: HTTP client for API calls.
            now: Current timestamp.

        Returns:
            CollectorResult with collected items.
        """
        state_machine = SourceStateMachine(
            source_id=source_config.id,
            run_id=self._run_id,
        )
        state_machine.to_fetching()

        max_items = self.resolve_max_items(
            source_config.max_items,
            max_items_override,
        )
        fetch_max_items = self.resolve_fetch_limit(
            max_items=max_items,
            fallback_limit=1000,
        )
        url = (
            f"{PAPERS_WITH_CODE_API_BASE_URL}{PAPERS_WITH_CODE_PAPERS_PATH}"
            f"?items_per_page={fetch_max_items}"
        )

        self._rate_limiter.acquire()

        result = http_client.fetch(
            source_id=source_config.id,
            url=url,
            extra_headers={"Accept": "application/json"},
        )

        if not result.is_success:
            self._log.warning(
                "api_request_failed",
                source_id=source_config.id,
                status_code=result.status_code,
            )
            state_machine.to_failed()
            return CollectorResult(
                items=[],
                state=state_machine.state,
            )

        state_machine.to_parsing()

        try:
            data = json.loads(result.body_bytes.decode("utf-8"))
            items = self._parse_response(data, source_config, now)

            # Filter by time: only keep items published in the last 24 hours
            items = self.filter_items_by_time(
                items=items,
                now=now,
                lookback_hours=lookback_hours,
                source_id=source_config.id,
            )
            items = self.enforce_max_items(items, max_items)

            state_machine.to_done()

            self._log.info(
                "collection_complete",
                source_id=source_config.id,
                items_collected=len(items),
            )

            return CollectorResult(
                items=items,
                state=state_machine.state,
            )

        except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
            self._log.warning(
                "parse_failed",
                source_id=source_config.id,
                error=str(e),
            )
            state_machine.to_failed()
            return CollectorResult(
                items=[],
                state=state_machine.state,
            )

    def _parse_response(
        self,
        data: dict[str, Any],
        source_config: SourceConfig,
        now: datetime,
    ) -> list[Item]:
        """Parse Papers With Code API response.

        Args:
            data: API response data.
            source_config: Source configuration.
            now: Current timestamp.

        Returns:
            List of parsed Items.
        """
        items: list[Item] = []
        results = data.get("results", [])

        for paper in results:
            item = self._parse_paper(paper, source_config, now)
            if item:
                items.append(item)

        return items

    def _parse_paper(
        self,
        paper: dict[str, Any],
        source_config: SourceConfig,
        now: datetime,
    ) -> Item | None:
        """Parse a single paper from API response.

        Args:
            paper: Paper data from API.
            source_config: Source configuration.
            now: Current timestamp.

        Returns:
            Parsed Item or None if invalid.
        """
        title = paper.get("title")
        url_or_id = paper.get("url_abs") or paper.get("id")

        if not title or not url_or_id:
            return None

        # Build canonical URL
        if url_or_id.startswith("http"):
            url = url_or_id
        else:
            url = f"https://paperswithcode.com/paper/{url_or_id}"

        url = self.canonicalize_url(url)

        # Extract arXiv ID
        arxiv_id = extract_arxiv_id(
            paper.get("url_abs"),
            paper.get("arxiv_id"),
        )

        # Parse publication date
        published_at = None
        date_confidence = DateConfidence.LOW
        if published := paper.get("published"):
            try:
                published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                date_confidence = DateConfidence.HIGH
            except (ValueError, TypeError):
                pass

        # Build raw_json with quality signals
        raw_json_data = {
            "platform": PLATFORM_PAPERS_WITH_CODE,
            "paper_id": paper.get("id"),
            "has_code": bool(paper.get("proceeding") or paper.get("repository_url")),
            "repository_url": paper.get("repository_url"),
            "proceeding": paper.get("proceeding"),
            "arxiv_id": arxiv_id,
            "authors": paper.get("authors", []),
            "abstract": paper.get("abstract", ""),
            "from_papers_with_code": True,
        }

        return Item(
            url=url,
            source_id=source_config.id,
            tier=source_config.tier,
            kind=source_config.kind,
            title=title,
            published_at=published_at,
            date_confidence=date_confidence,
            content_hash=compute_content_hash(title=title, url=url),
            raw_json=json.dumps(raw_json_data, ensure_ascii=False),
            first_seen_at=now,
            last_seen_at=now,
        )
