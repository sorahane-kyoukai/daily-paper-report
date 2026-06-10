"""HTTP fetch layer with caching, retries, and failure isolation.

This module provides robust HTTP fetch operations with:
- ETag/Last-Modified conditional requests for caching
- Configurable retry policy with exponential backoff
- Maximum response size enforcement
- Header redaction for security
- Metrics collection for observability
"""

from src.features.fetch.cache import CacheManager
from src.features.fetch.client import HttpFetcher
from src.features.fetch.config import DomainProfile, FetchConfig
from src.features.fetch.constants import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_RESPONSE_SIZE_BYTES,
    HTTP_STATUS_NOT_MODIFIED,
    HTTP_STATUS_OK_MAX,
    HTTP_STATUS_OK_MIN,
    HTTP_STATUS_TOO_MANY_REQUESTS,
    MAX_RETRY_AFTER_SECONDS,
)
from src.features.fetch.metrics import FetchMetrics
from src.features.fetch.models import (
    FetchError,
    FetchErrorClass,
    FetchResult,
    ResponseSizeExceededError,
    RetryPolicy,
)
from src.features.fetch.redact import redact_headers, redact_url_credentials


__all__ = [
    # Client
    "HttpFetcher",
    # Cache
    "CacheManager",
    # Config
    "FetchConfig",
    "DomainProfile",
    # Models
    "FetchResult",
    "FetchError",
    "FetchErrorClass",
    "RetryPolicy",
    "ResponseSizeExceededError",
    # Constants
    "HTTP_STATUS_OK_MIN",
    "HTTP_STATUS_OK_MAX",
    "HTTP_STATUS_NOT_MODIFIED",
    "HTTP_STATUS_TOO_MANY_REQUESTS",
    "DEFAULT_MAX_RESPONSE_SIZE_BYTES",
    "DEFAULT_CHUNK_SIZE",
    "MAX_RETRY_AFTER_SECONDS",
    # Metrics
    "FetchMetrics",
    # Redaction
    "redact_headers",
    "redact_url_credentials",
]
