"""Full-paper acquisition and local extraction cache."""

from src.features.fulltext.models import FullTextDocument, FullTextStatus
from src.features.fulltext.service import FullTextService


__all__ = ["FullTextDocument", "FullTextService", "FullTextStatus"]
