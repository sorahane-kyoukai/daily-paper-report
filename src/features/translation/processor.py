"""Batch LLM translation orchestrator for Traditional Chinese."""

from __future__ import annotations

import json
import os
from pathlib import Path

import structlog

from src.features.llm.errors import LlmApiError, LlmProcessingError
from src.features.llm.json_utils import (
    json_candidates,
    strip_markdown_fences,
    try_parse_json_array,
)
from src.features.llm.protocols import LlmClient
from src.features.translation.models import (
    CURRENT_TRANSLATION_PROMPT_VERSION,
    TranslationCache,
    TranslationEntry,
)
from src.features.translation.prompts import (
    SYSTEM_INSTRUCTION,
    build_translation_prompt,
)


logger = structlog.get_logger()

DEFAULT_BATCH_SIZE = 1
BATCH_SIZE = DEFAULT_BATCH_SIZE
MAX_BATCH_SIZE = 1
_MAX_BATCH_RETRIES = 1
_MAX_SINGLE_RETRIES = 2
_MAX_RAW_RESPONSE_LOG_LEN = 300


def _resolve_batch_size() -> int:
    """Resolve translation batch size from environment with safe bounds."""
    raw = (
        os.getenv("LLM_TRANSLATION_BATCH_SIZE")
        or os.getenv("TRANSLATION_BATCH_SIZE")
        or os.getenv("LLM_BATCH_SIZE")
    )
    if not raw:
        return DEFAULT_BATCH_SIZE
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_BATCH_SIZE
    return max(1, min(value, MAX_BATCH_SIZE))


class TranslationProcessor:
    """Orchestrates batch LLM translation of story titles and summaries.

    Translates stories to Traditional Chinese using the same
    client and batch/cache/retry patterns established by the
    LlmRelevanceProcessor.
    """

    def __init__(
        self,
        client: LlmClient,
        output_dir: Path,
    ) -> None:
        """Initialize the translation processor.

        Args:
            client: Any LLM client implementing the LlmClient protocol.
            output_dir: Output directory for cache file storage.
        """
        self._client = client
        self._model = client.model
        self._cache = TranslationCache(output_dir / "api" / "translations_zh.json")
        self._log = logger.bind(component="translation", subcomponent="processor")

    def translate(
        self, stories: list[dict[str, object]]
    ) -> dict[str, TranslationEntry]:
        """Translate all stories, skipping those already cached.

        Args:
            stories: Story dicts (from to_json_dict), each with at
                     minimum 'story_id', 'title', and optionally 'summary'.

        Returns:
            Map of story_id to TranslationEntry for all stories
            (cached + newly translated).
        """
        self._cache.load()

        uncached = [
            s
            for s in stories
            if not self._cache.is_current(
                str(s.get("story_id", "")),
                fulltext_sha256=str(s.get("fulltext_sha256", "")),
                model=self._model,
            )
        ]
        stale_cached = [
            s
            for s in stories
            if self._cache.has(str(s.get("story_id", "")))
            and not self._cache.is_current(
                str(s.get("story_id", "")),
                fulltext_sha256=str(s.get("fulltext_sha256", "")),
                model=self._model,
            )
        ]

        self._log.info(
            "translation_started",
            total=len(stories),
            cached=len(stories) - len(uncached),
            stale_cached=len(stale_cached),
            prompt_version=CURRENT_TRANSLATION_PROMPT_VERSION,
            to_translate=len(uncached),
        )

        if uncached:
            batch_size = _resolve_batch_size()
            self._log.info(
                "translation_batching",
                batch_size=batch_size,
                batches=(len(uncached) + batch_size - 1) // batch_size,
            )
            batches = _create_batches(uncached, batch_size)
            for batch_idx, batch in enumerate(batches):
                self._process_batch(batch, batch_idx)
                self._cache.save()

            self._cache.save()

        return dict(self._cache.entries)

    def _process_batch(
        self,
        batch: list[dict[str, object]],
        batch_idx: int,
    ) -> None:
        """Process a single batch of stories for translation.

        On failure or partial result, recursively splits the missing
        stories into smaller batches. This avoids turning a provider
        response-size failure into an expensive one-request-per-story
        fallback unless the batch has already been reduced to one story.

        Args:
            batch: Story dicts in this batch.
            batch_idx: Batch index for logging.
        """
        total_translated = self._process_batch_adaptive(
            batch=batch,
            batch_idx=batch_idx,
            attempt=0,
        )
        failed_ids = [
            str(s.get("story_id", ""))
            for s in batch
            if not self._cache.is_current(
                str(s.get("story_id", "")),
                fulltext_sha256=str(s.get("fulltext_sha256", "")),
                model=self._model,
            )
        ]
        self._log.info(
            "translation_batch_complete",
            batch=batch_idx,
            translated=total_translated,
            batch_size=len(batch),
            failed_ids=failed_ids,
        )

    def _process_batch_adaptive(
        self,
        batch: list[dict[str, object]],
        batch_idx: int,
        attempt: int,
    ) -> int:
        """Translate a batch, splitting failures into smaller batches.

        Args:
            batch: Story dicts to translate.
            batch_idx: Original top-level batch index for logging.
            attempt: Adaptive retry depth.

        Returns:
            Number of newly translated entries written to the cache.
        """
        if not batch:
            return 0

        entries = self._attempt_batch(batch, batch_idx, attempt=attempt)
        translated = 0
        for entry in entries:
            if not self._cache.is_current(
                entry.story_id,
                fulltext_sha256=entry.fulltext_sha256,
                model=self._model,
            ):
                translated += 1
            self._cache.put(entry)

        missing = [
            s
            for s in batch
            if not self._cache.is_current(
                str(s.get("story_id", "")),
                fulltext_sha256=str(s.get("fulltext_sha256", "")),
                model=self._model,
            )
        ]
        if not missing:
            return translated

        if len(missing) == 1:
            story = missing[0]
            if attempt < _MAX_SINGLE_RETRIES:
                self._log.warning(
                    "translation_story_retry",
                    batch=batch_idx,
                    attempt=attempt + 1,
                    story_id=str(story.get("story_id", "")),
                )
                return translated + self._process_batch_adaptive(
                    missing,
                    batch_idx,
                    attempt + 1,
                )
            self._log.warning(
                "translation_story_failed",
                batch=batch_idx,
                attempt=attempt,
                story_id=str(story.get("story_id", "")),
                title=str(story.get("title", ""))[:120],
            )
            return translated

        midpoint = max(1, len(missing) // 2)
        left = missing[:midpoint]
        right = missing[midpoint:]
        self._log.warning(
            "translation_batch_splitting",
            batch=batch_idx,
            attempt=attempt,
            missing=len(missing),
            left=len(left),
            right=len(right),
        )
        return (
            translated
            + self._process_batch_adaptive(left, batch_idx, attempt + 1)
            + self._process_batch_adaptive(right, batch_idx, attempt + 1)
        )

    def _attempt_batch(
        self,
        batch: list[dict[str, object]],
        batch_idx: int,
        attempt: int,
    ) -> list[TranslationEntry]:
        """Make a single translation attempt for a batch.

        Args:
            batch: Story dicts to translate.
            batch_idx: Batch index for logging.
            attempt: Attempt number (0=first, 1=retry, 2=single fallback).

        Returns:
            List of successfully parsed TranslationEntry objects.
        """
        prompt = build_translation_prompt(batch)
        story_ids = [str(s.get("story_id", "")) for s in batch]
        recoverable = len(batch) > 1

        try:
            raw_response = self._client.generate_content(
                prompt=prompt,
                system_instruction=SYSTEM_INSTRUCTION,
            )
        except LlmApiError as exc:
            self._log.warning(
                "translation_batch_api_retry"
                if recoverable
                else "translation_batch_api_error",
                batch=batch_idx,
                attempt=attempt,
                batch_size=len(batch),
                story_ids=story_ids,
                error=str(exc),
            )
            return []

        try:
            entries = self._parse_response(raw_response, batch)
        except LlmProcessingError as exc:
            self._log.warning(
                "translation_batch_parse_retry"
                if recoverable
                else "translation_batch_parse_error",
                batch=batch_idx,
                attempt=attempt,
                batch_size=len(batch),
                story_ids=story_ids,
                error=str(exc),
                raw_response_preview=raw_response[:_MAX_RAW_RESPONSE_LOG_LEN],
            )
            return []

        if not entries and batch:
            self._log.warning(
                "translation_batch_empty_retry"
                if recoverable
                else "translation_batch_empty_result",
                batch=batch_idx,
                attempt=attempt,
                batch_size=len(batch),
                story_ids=story_ids,
                raw_response_preview=raw_response[:_MAX_RAW_RESPONSE_LOG_LEN],
            )

        return entries

    def _parse_response(
        self,
        raw_response: str,
        batch: list[dict[str, object]],
    ) -> list[TranslationEntry]:
        """Parse the LLM JSON response into TranslationEntry objects.

        Args:
            raw_response: Raw text response from the LLM.
            batch: Original batch for validation.

        Returns:
            List of parsed TranslationEntry objects.

        Raises:
            LlmProcessingError: If response cannot be parsed.
        """
        text = strip_markdown_fences(raw_response)

        parsed: list[dict[str, object]] | None = None
        try:
            response_object = json.loads(text)
        except json.JSONDecodeError:
            response_object = None
        if isinstance(response_object, dict) and isinstance(
            response_object.get("translations"), list
        ):
            parsed = [
                item
                for item in response_object["translations"]
                if isinstance(item, dict)
            ]
        for candidate in json_candidates(text):
            if parsed is not None:
                break
            parsed = try_parse_json_array(candidate)
            if parsed is not None:
                break

        if parsed is None:
            msg = f"Failed to parse translation response: {text[:200]}"
            raise LlmProcessingError(msg)

        valid_ids = {str(s.get("story_id", "")) for s in batch}
        results: list[TranslationEntry] = []

        for item in parsed:
            if not isinstance(item, dict):
                continue

            story_id = _resolve_story_id(str(item.get("id", "")), batch, valid_ids)
            if story_id not in valid_ids:
                continue

            title_zh = str(item.get("title_zh", ""))
            summary_zh = str(item.get("summary_zh", ""))

            if not title_zh:
                continue

            results.append(
                TranslationEntry(
                    story_id=story_id,
                    title_zh=title_zh,
                    summary_zh=summary_zh,
                    model=self._model,
                    fulltext_sha256=str(
                        next(
                            (
                                story.get("fulltext_sha256", "")
                                for story in batch
                                if str(story.get("story_id", "")) == story_id
                            ),
                            "",
                        )
                    ),
                )
            )

        return results


def _resolve_story_id(
    raw_id: str,
    batch: list[dict[str, object]],
    valid_ids: set[str],
) -> str:
    """Resolve provider-returned id to a story_id.

    LLM providers may follow the prompt's numbered list or omit a namespace prefix.
    Accept only unambiguous recovery within the current batch.
    """
    story_id = raw_id.strip()
    if story_id.startswith("[") and story_id.endswith("]"):
        story_id = story_id[1:-1].strip()
    if story_id in valid_ids:
        return story_id

    suffix_matches = [
        candidate for candidate in valid_ids if candidate.rsplit(":", 1)[-1] == story_id
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    if story_id.isdigit():
        index = int(story_id) - 1
        if 0 <= index < len(batch):
            return str(batch[index].get("story_id", ""))

    return story_id


def _create_batches(
    items: list[dict[str, object]], batch_size: int
) -> list[list[dict[str, object]]]:
    """Split items into fixed-size batches.

    Args:
        items: Items to batch.
        batch_size: Maximum items per batch.

    Returns:
        List of item batches.
    """
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
