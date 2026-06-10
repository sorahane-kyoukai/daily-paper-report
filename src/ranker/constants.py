"""Constants for the ranker module."""

# Default kind weights (can be overridden by config)
DEFAULT_KIND_WEIGHTS: dict[str, float] = {
    "blog": 1.5,  # Official blogs are important
    "paper": 1.2,  # Research papers
    "model": 1.8,  # Model releases are high priority
    "release": 1.6,  # Software releases
    "news": 0.8,  # News aggregation
    "docs": 1.0,  # Documentation
    "forum": 0.6,  # Forum discussions
    "social": 0.5,  # Social media
}

# ArXiv category patterns for per-category quota
ARXIV_CATEGORY_PATTERNS: list[str] = [
    "cs.AI",
    "cs.LG",
    "cs.CL",
    "cs.CV",
    "cs.IR",
    "cs.MA",
    "cs.RO",
    "cs.SE",
    "stat.ML",
]

# Days for recency calculation
MAX_RECENCY_DAYS: int = 30

# Quality signal sources for cross-source scoring.
# Papers appearing in these curated/targeted sources get a bonus
# because editorial selection or keyword targeting indicates relevance.
QUALITY_SIGNAL_SOURCES: frozenset[str] = frozenset(
    {
        # Curated aggregators
        "papers_with_code",
        "hf_daily_papers",
        # arXiv API keyword queries (targeted search = relevance signal)
        "arxiv-api-llm",
        "arxiv-api-agents",
        "arxiv-api-reasoning",
        "arxiv-api-alignment",
        "arxiv-api-multimodal",
    }
)

# Maximum cross-source score to prevent overfitting
CROSS_SOURCE_SCORE_CAP: float = 3.0
