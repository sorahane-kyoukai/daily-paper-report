"""arXiv collectors for RSS feeds and API queries.

This module provides collectors for ingesting arXiv papers via:
- RSS/Atom feeds for category subscriptions (cs.AI, cs.LG, cs.CL, stat.ML)
- arXiv API for keyword-based queries

All arXiv URLs are normalized to canonical format: https://arxiv.org/abs/<id>
"""

from src.collectors.arxiv.api import ArxivApiCollector
from src.collectors.arxiv.deduper import ArxivDeduplicator
from src.collectors.arxiv.rss import ArxivRssCollector
from src.collectors.arxiv.utils import (
    extract_arxiv_id,
    normalize_arxiv_url,
)


__all__ = [
    "ArxivApiCollector",
    "ArxivDeduplicator",
    "ArxivRssCollector",
    "extract_arxiv_id",
    "normalize_arxiv_url",
]
