"""Base schema types for configuration."""

from enum import Enum


class SourceTier(int, Enum):
    """Source tier classification.

    Tier 0: Primary/first-hand sources (official blogs, releases)
    Tier 1: Secondary sources (aggregators, news)
    Tier 2: Tertiary sources (social media, forums)
    """

    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2


class SourceMethod(str, Enum):
    """Source ingestion method."""

    RSS_ATOM = "rss_atom"
    ARXIV_API = "arxiv_api"
    OPENREVIEW_VENUE = "openreview_venue"
    GITHUB_RELEASES = "github_releases"
    HF_ORG = "hf_org"
    HTML_LIST = "html_list"
    HTML_SINGLE = "html_single"
    STATUS_ONLY = "status_only"
    PAPERS_WITH_CODE = "papers_with_code"
    HF_DAILY_PAPERS = "hf_daily_papers"


class SourceKind(str, Enum):
    """Source content kind classification."""

    BLOG = "blog"
    PAPER = "paper"
    MODEL = "model"
    RELEASE = "release"
    NEWS = "news"
    DOCS = "docs"
    FORUM = "forum"
    SOCIAL = "social"


class LinkType(str, Enum):
    """Known link types for entity prefer_links."""

    OFFICIAL = "official"
    ARXIV = "arxiv"
    GITHUB = "github"
    HUGGINGFACE = "huggingface"
    MODELSCOPE = "modelscope"
    OPENREVIEW = "openreview"
    PAPER = "paper"
    BLOG = "blog"
    DOCS = "docs"
    DEMO = "demo"
    VIDEO = "video"
    TWITTER = "twitter"
    WEIBO = "weibo"
