"""HuggingFace Daily Papers collector for quality signal papers."""

import json
from datetime import datetime
from typing import Any

import structlog

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.platform.constants import (
    HF_DAILY_PAPERS_API_URL,
    HF_DAILY_PAPERS_DEFAULT_MAX_QPS,
    PLATFORM_HF_DAILY_PAPERS,
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


class HuggingFaceDailyPapersCollector(BaseCollector):
    """Collector for HuggingFace Daily Papers.

    Fetches papers from HuggingFace's daily curated paper list,
    which represents high-quality, community-endorsed papers.
    """

    def __init__(
        self,
        strip_params: list[str] | None = None,
        run_id: str = "",
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        """Initialize the HuggingFace Daily Papers collector.

        Args:
            strip_params: URL parameters to strip for canonicalization.
            run_id: Run identifier for logging.
            rate_limiter: Rate limiter for API throttling.
        """
        super().__init__(strip_params)
        self._run_id = run_id
        self._metrics = PlatformMetrics.get_instance()
        self._rate_limiter = rate_limiter or get_platform_rate_limiter(
            platform=PLATFORM_HF_DAILY_PAPERS,
            max_qps=HF_DAILY_PAPERS_DEFAULT_MAX_QPS,
        )
        self._log = logger.bind(
            component="collector",
            subcomponent="hf_daily_papers",
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
        """Collect papers from HuggingFace Daily Papers API.

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

        self._rate_limiter.acquire()

        result = http_client.fetch(
            source_id=source_config.id,
            url=HF_DAILY_PAPERS_API_URL,
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
            max_items = self.resolve_max_items(
                source_config.max_items,
                max_items_override,
            )
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
        data: list[dict[str, Any]] | dict[str, Any],
        source_config: SourceConfig,
        now: datetime,
    ) -> list[Item]:
        """Parse HuggingFace Daily Papers API response.

        Args:
            data: API response data (list of papers or dict with results).
            source_config: Source configuration.
            now: Current timestamp.

        Returns:
            List of parsed Items.
        """
        items: list[Item] = []

        # Handle both list and dict response formats
        papers = data if isinstance(data, list) else data.get("papers", [])

        for paper in papers:
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
        # Handle nested paper structure
        paper_data = paper.get("paper", paper)

        title = paper_data.get("title")
        paper_id = paper_data.get("id") or paper_data.get("paperId")

        if not title or not paper_id:
            return None

        # Build arXiv URL
        arxiv_id = paper_id
        url = f"https://arxiv.org/abs/{arxiv_id}"
        url = self.canonicalize_url(url)

        # Parse publication date
        published_at = None
        date_confidence = DateConfidence.LOW
        if published := paper_data.get("publishedAt") or paper.get("publishedAt"):
            try:
                published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                date_confidence = DateConfidence.HIGH
            except (ValueError, TypeError):
                pass

        # Get upvotes as quality signal
        upvotes = paper.get("upvotes", 0)

        # Build raw_json with quality signals
        raw_json_data = {
            "platform": PLATFORM_HF_DAILY_PAPERS,
            "arxiv_id": arxiv_id,
            "upvotes": upvotes,
            "authors": paper_data.get("authors", []),
            "summary": paper_data.get("summary", ""),
            "abstract": paper_data.get("summary", ""),
            "from_hf_daily_papers": True,
            "is_trending": upvotes > 0,
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
