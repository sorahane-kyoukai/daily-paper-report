"""Data models for translation results and caching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from src.features.translation.prompts import CURRENT_TRANSLATION_PROMPT_VERSION


__all__ = ["CURRENT_TRANSLATION_PROMPT_VERSION", "TranslationCache", "TranslationEntry"]

logger = structlog.get_logger()


@dataclass(frozen=True)
class TranslationEntry:
    """Translation result for a single story.

    Attributes:
        story_id: Identifier of the translated story.
        title_zh: Traditional Chinese title.
        summary_zh: Traditional Chinese summary.
        prompt_version: Prompt/cache version used to produce this entry.
    """

    story_id: str
    title_zh: str
    summary_zh: str
    prompt_version: str = CURRENT_TRANSLATION_PROMPT_VERSION
    fulltext_sha256: str = ""
    model: str = "deepseek-v4-flash"

    def to_dict(self) -> dict[str, str]:
        """Serialize to a JSON-compatible dictionary.

        Returns:
            Dictionary with story_id, title_zh, summary_zh, and prompt_version.
        """
        return {
            "story_id": self.story_id,
            "title_zh": self.title_zh,
            "summary_zh": self.summary_zh,
            "prompt_version": self.prompt_version,
            "fulltext_sha256": self.fulltext_sha256,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> TranslationEntry:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with story_id, title_zh, summary_zh keys.

        Returns:
            TranslationEntry instance.
        """
        return cls(
            story_id=data["story_id"],
            title_zh=data.get("title_zh", ""),
            summary_zh=data.get("summary_zh", ""),
            prompt_version=data.get("prompt_version", ""),
            fulltext_sha256=data.get("fulltext_sha256", ""),
            model=data.get("model", ""),
        )


class TranslationCache:
    """Manages persistent cache of translations in a JSON file.

    Stores translations as a dict mapping story_id to TranslationEntry,
    serialized to ``api/translations_zh.json``.
    """

    def __init__(self, cache_path: Path) -> None:
        """Initialize the translation cache.

        Args:
            cache_path: Path to the JSON cache file.
        """
        self._path = cache_path
        self._entries: dict[str, TranslationEntry] = {}
        self._log = logger.bind(component="translation", subcomponent="cache")

    @property
    def entries(self) -> dict[str, TranslationEntry]:
        """Return the current cache entries."""
        return self._entries

    def load(self) -> None:
        """Load cached translations from disk.

        Silently handles missing or corrupt cache files.
        """
        if not self._path.exists():
            self._log.debug("translation_cache_not_found", path=str(self._path))
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for story_id, entry_data in raw.items():
                if isinstance(entry_data, dict):
                    entry_data.setdefault("story_id", story_id)
                    self._entries[story_id] = TranslationEntry.from_dict(entry_data)
            self._log.info(
                "translation_cache_loaded",
                count=len(self._entries),
                path=str(self._path),
            )
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            self._log.warning(
                "translation_cache_load_failed",
                path=str(self._path),
                error=str(exc),
            )

    def save(self) -> None:
        """Persist current cache entries to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: entry.to_dict() for sid, entry in self._entries.items()}
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._log.info(
            "translation_cache_saved",
            count=len(self._entries),
            path=str(self._path),
        )

    def has(self, story_id: str) -> bool:
        """Check if a story has a cached translation.

        Args:
            story_id: Story identifier to look up.

        Returns:
            True if cached translation exists.
        """
        return story_id in self._entries

    def is_current(
        self,
        story_id: str,
        prompt_version: str = CURRENT_TRANSLATION_PROMPT_VERSION,
        fulltext_sha256: str | None = None,
    ) -> bool:
        """Check whether a story has a cached translation for this prompt version.

        Args:
            story_id: Story identifier to look up.
            prompt_version: Required prompt/cache version.

        Returns:
            True when the cached translation exists and matches prompt_version.
        """
        entry = self._entries.get(story_id)
        return bool(
            entry is not None
            and entry.prompt_version == prompt_version
            and entry.model == "deepseek-v4-flash"
            and (fulltext_sha256 is None or entry.fulltext_sha256 == fulltext_sha256)
        )

    def get(self, story_id: str) -> TranslationEntry | None:
        """Retrieve a cached translation.

        Args:
            story_id: Story identifier.

        Returns:
            TranslationEntry if cached, None otherwise.
        """
        return self._entries.get(story_id)

    def put(self, entry: TranslationEntry) -> None:
        """Add or update a cached translation.

        Args:
            entry: Translation entry to cache.
        """
        self._entries[entry.story_id] = entry
