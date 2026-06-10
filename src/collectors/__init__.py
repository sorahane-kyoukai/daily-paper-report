"""Collector framework for ingesting data from heterogeneous sources."""

from src.collectors.base import BaseCollector, Collector, CollectorResult
from src.collectors.errors import (
    CollectorError,
    CollectorErrorClass,
    ErrorRecord,
    ParseError,
    SchemaError,
)
from src.collectors.html_list import HtmlListCollector
from src.collectors.metrics import CollectorMetrics
from src.collectors.platform.github import GitHubReleasesCollector
from src.collectors.platform.huggingface import HuggingFaceOrgCollector
from src.collectors.platform.metrics import PlatformMetrics
from src.collectors.platform.openreview import OpenReviewVenueCollector
from src.collectors.platform.rate_limiter import TokenBucketRateLimiter
from src.collectors.rss_atom import RssAtomCollector
from src.collectors.runner import CollectorRunner, RunnerResult, SourceRunResult
from src.collectors.state_machine import (
    SourceState,
    SourceStateMachine,
    SourceStateTransitionError,
)


__all__ = [
    "BaseCollector",
    "Collector",
    "CollectorError",
    "CollectorErrorClass",
    "CollectorMetrics",
    "CollectorResult",
    "CollectorRunner",
    "ErrorRecord",
    "GitHubReleasesCollector",
    "HtmlListCollector",
    "HuggingFaceOrgCollector",
    "OpenReviewVenueCollector",
    "ParseError",
    "PlatformMetrics",
    "RssAtomCollector",
    "RunnerResult",
    "SchemaError",
    "SourceRunResult",
    "SourceState",
    "SourceStateMachine",
    "SourceStateTransitionError",
    "TokenBucketRateLimiter",
]
