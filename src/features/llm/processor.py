"""Batch LLM evaluation orchestrator for paper relevance scoring."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import structlog

from src.features.config.schemas.topics import TopicConfig
from src.features.llm.errors import LlmApiError, LlmProcessingError
from src.features.llm.json_utils import (
    json_candidates,
    strip_markdown_fences,
    try_parse_json_array,
)
from src.features.llm.models import LlmPhaseResult, LlmRelevanceResult
from src.features.llm.prompts import SYSTEM_INSTRUCTION, build_batch_prompt
from src.features.llm.protocols import LlmClient
from src.linker.models import Story


logger = structlog.get_logger()

DEFAULT_BATCH_SIZE = 5
BATCH_SIZE = DEFAULT_BATCH_SIZE
MAX_BATCH_SIZE = 50
DEFAULT_CONCURRENCY = 1
MAX_CONCURRENCY = 8
_NEUTRAL_SCORE = 0.5


def _resolve_batch_size() -> int:
    """Resolve LLM relevance batch size from environment with safe bounds."""
    raw = os.getenv("LLM_RELEVANCE_BATCH_SIZE") or os.getenv("LLM_BATCH_SIZE")
    if not raw:
        return DEFAULT_BATCH_SIZE
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_BATCH_SIZE
    return max(1, min(value, MAX_BATCH_SIZE))


def _resolve_concurrency() -> int:
    """Resolve LLM relevance batch concurrency from environment."""
    raw = os.getenv("LLM_RELEVANCE_CONCURRENCY") or os.getenv("LLM_MAX_CONCURRENCY")
    if not raw:
        return DEFAULT_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CONCURRENCY
    return max(1, min(value, MAX_CONCURRENCY))


class LlmRelevanceProcessor:
    """Orchestrates batch LLM evaluation of stories.

    Filters stories to those with meaningful content (papers with
    abstracts), batches them, sends to the Gemini API, and parses
    the structured JSON responses.
    """

    def __init__(
        self,
        client: LlmClient,
        topics: list[TopicConfig],
    ) -> None:
        """Initialize the processor.

        Args:
            client: Any LLM client implementing the LlmClient protocol.
            topics: Topic configurations for relevance evaluation.
        """
        self._client = client
        self._topics = topics
        self._log = logger.bind(component="llm", subcomponent="processor")

    def evaluate_stories(self, stories: list[Story]) -> LlmPhaseResult:
        """Evaluate all stories for relevance using the LLM.

        Stories without abstracts or arxiv_ids are skipped as they
        lack sufficient content for meaningful evaluation.

        Args:
            stories: Stories from the linker phase.

        Returns:
            LlmPhaseResult with scores and audit trail.
        """
        result = LlmPhaseResult()

        evaluatable, skipped = self._partition_stories(stories)
        result.stories_skipped = skipped

        if not evaluatable:
            self._log.info("llm_no_evaluatable_stories")
            return result

        batch_size = _resolve_batch_size()
        concurrency = _resolve_concurrency()
        batches = self._create_batches(evaluatable, batch_size=batch_size)
        self._log.info(
            "llm_evaluation_started",
            stories=len(evaluatable),
            batches=len(batches),
            batch_size=batch_size,
            concurrency=concurrency,
        )

        if concurrency == 1 or len(batches) <= 1:
            for batch_idx, batch in enumerate(batches):
                self._process_batch(batch, batch_idx, result)
        else:
            self._process_batches_concurrently(batches, concurrency, result)

        self._log.info(
            "llm_evaluation_complete",
            evaluated=result.stories_evaluated,
            skipped=result.stories_skipped,
            api_calls=result.api_calls_made,
            errors=len(result.errors),
        )

        return result

    def _partition_stories(self, stories: list[Story]) -> tuple[list[Story], int]:
        """Split stories into evaluatable and skipped.

        A story is evaluatable if it has an arxiv_id or at least one
        raw item with abstract/summary content.

        Args:
            stories: All input stories.

        Returns:
            Tuple of (evaluatable stories, skip count).
        """
        evaluatable: list[Story] = []
        skipped = 0

        for story in stories:
            if story.arxiv_id or self._has_abstract(story):
                evaluatable.append(story)
            else:
                skipped += 1

        return evaluatable, skipped

    @staticmethod
    def _has_abstract(story: Story) -> bool:
        """Check if a story has abstract content in its raw items."""
        for item in story.raw_items:
            try:
                raw = json.loads(item.raw_json)
            except (json.JSONDecodeError, TypeError):
                continue
            for field_name in ("abstract_snippet", "summary"):
                if isinstance(raw.get(field_name), str) and raw[field_name]:
                    return True
        return False

    @staticmethod
    def _create_batches(
        stories: list[Story],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> list[list[Story]]:
        """Split stories into batches of BATCH_SIZE.

        Args:
            stories: Stories to batch.

        Returns:
            List of story batches.
        """
        return [stories[i : i + batch_size] for i in range(0, len(stories), batch_size)]

    def _process_batch(
        self,
        batch: list[Story],
        batch_idx: int,
        result: LlmPhaseResult,
    ) -> None:
        """Process a single batch of stories.

        On failure, adaptively splits the batch before falling back to
        neutral scores. This avoids letting one provider truncation or
        malformed response flatten an entire 25-50 story batch to 0.5.

        Args:
            batch: Stories in this batch.
            batch_idx: Batch index for logging.
            result: Accumulated phase result (mutated in place).
        """
        self._merge_phase_result(
            result,
            self._process_batch_to_result(batch, batch_idx),
        )

    def _process_batches_concurrently(
        self,
        batches: list[list[Story]],
        concurrency: int,
        result: LlmPhaseResult,
    ) -> None:
        """Process LLM batches concurrently and merge deterministic results."""
        completed: list[tuple[int, LlmPhaseResult]] = []

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(
                    self._process_batch_to_result,
                    batch,
                    batch_idx,
                ): batch_idx
                for batch_idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    batch_result = future.result()
                except Exception as exc:  # noqa: BLE001
                    self._log.warning(
                        "llm_batch_unexpected_error",
                        batch=batch_idx,
                        error=str(exc),
                    )
                    batch_result = LlmPhaseResult()
                    batch_result.errors.append(
                        f"Batch {batch_idx} unexpected error: {exc}"
                    )
                    self._assign_neutral_scores(batches[batch_idx], batch_result)
                completed.append((batch_idx, batch_result))

        for _batch_idx, batch_result in sorted(completed, key=lambda item: item[0]):
            self._merge_phase_result(result, batch_result)

    def _process_batch_to_result(
        self,
        batch: list[Story],
        batch_idx: int,
    ) -> LlmPhaseResult:
        """Process a single batch and return an isolated phase result."""
        return self._process_batch_adaptive(batch, batch_idx, attempt=0)

    def _process_batch_adaptive(
        self,
        batch: list[Story],
        batch_idx: int,
        attempt: int,
    ) -> LlmPhaseResult:
        """Process a batch, splitting recoverable failures into smaller chunks."""
        result = LlmPhaseResult()
        if not batch:
            return result

        attempt_result = self._attempt_batch_once(
            batch=batch,
            batch_idx=batch_idx,
            attempt=attempt,
            recoverable=len(batch) > 1,
        )
        self._merge_phase_result(result, attempt_result)

        missing = [story for story in batch if story.story_id not in result.scores]
        if not missing:
            return result

        if len(missing) == 1:
            story = missing[0]
            self._log.warning(
                "llm_story_failed",
                batch=batch_idx,
                attempt=attempt,
                story_id=story.story_id,
                title=story.title[:120],
            )
            if not attempt_result.errors:
                result.errors.append(
                    f"Story {story.story_id} missing from LLM response"
                )
            self._assign_neutral_scores(missing, result)
            return result

        midpoint = max(1, len(missing) // 2)
        left = missing[:midpoint]
        right = missing[midpoint:]
        self._log.warning(
            "llm_batch_splitting",
            batch=batch_idx,
            attempt=attempt,
            missing=len(missing),
            left=len(left),
            right=len(right),
        )
        self._merge_phase_result(
            result,
            self._process_batch_adaptive(left, batch_idx, attempt + 1),
        )
        self._merge_phase_result(
            result,
            self._process_batch_adaptive(right, batch_idx, attempt + 1),
        )
        return result

    def _attempt_batch_once(
        self,
        batch: list[Story],
        batch_idx: int,
        attempt: int,
        recoverable: bool,
    ) -> LlmPhaseResult:
        """Attempt exactly one LLM request without batch-level neutral fallback."""
        result = LlmPhaseResult()
        prompt = build_batch_prompt(batch, self._topics)

        try:
            raw_response = self._client.generate_content(
                prompt=prompt,
                system_instruction=SYSTEM_INSTRUCTION,
            )
            result.api_calls_made += 1
        except LlmApiError as exc:
            error_msg = f"Batch {batch_idx} API error: {exc}"
            self._log.warning(
                "llm_batch_api_retry" if recoverable else "llm_batch_api_error",
                batch=batch_idx,
                attempt=attempt,
                batch_size=len(batch),
                error=str(exc),
            )
            if not recoverable:
                result.errors.append(error_msg)
            return result

        try:
            parsed = self._parse_response(raw_response, batch)
        except LlmProcessingError as exc:
            error_msg = f"Batch {batch_idx} parse error: {exc}"
            self._log.warning(
                "llm_batch_parse_retry" if recoverable else "llm_batch_parse_error",
                batch=batch_idx,
                attempt=attempt,
                batch_size=len(batch),
                error=str(exc),
            )
            if not recoverable:
                result.errors.append(error_msg)
            return result

        for llm_result in parsed:
            result.scores[llm_result.story_id] = llm_result.relevance_score
            result.results.append(llm_result)
            result.stories_evaluated += 1

        return result

    @staticmethod
    def _merge_phase_result(
        target: LlmPhaseResult,
        source: LlmPhaseResult,
    ) -> None:
        """Merge one isolated batch result into the accumulated phase result."""
        target.scores.update(source.scores)
        target.results.extend(source.results)
        target.stories_evaluated += source.stories_evaluated
        target.stories_skipped += source.stories_skipped
        target.api_calls_made += source.api_calls_made
        target.errors.extend(source.errors)

    def _parse_response(
        self,
        raw_response: str,
        batch: list[Story],
    ) -> list[LlmRelevanceResult]:
        """Parse the LLM JSON response into structured results.

        Handles common response quirks: markdown code fences, extra
        whitespace, and partial JSON arrays.

        Args:
            raw_response: Raw text response from the LLM.
            batch: Original batch for validation context.

        Returns:
            List of parsed LlmRelevanceResult objects.

        Raises:
            LlmProcessingError: If response cannot be parsed at all.
        """
        text = strip_markdown_fences(raw_response)

        entries = self._robust_json_parse(text)

        if not isinstance(entries, list):
            msg = f"Expected JSON array, got {type(entries).__name__}"
            raise LlmProcessingError(msg)

        valid_ids = {s.story_id for s in batch}
        results: list[LlmRelevanceResult] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            story_id = str(entry.get("id", ""))
            if story_id not in valid_ids:
                continue

            score = _clamp_score(entry.get("score", 0.5))
            rationale = str(entry.get("rationale", ""))
            topics_raw = entry.get("topics", [])
            topics = (
                [str(t) for t in topics_raw] if isinstance(topics_raw, list) else []
            )

            results.append(
                LlmRelevanceResult(
                    story_id=story_id,
                    relevance_score=score,
                    rationale=rationale,
                    topics_matched=topics,
                )
            )

        return results

    @staticmethod
    def _robust_json_parse(text: str) -> list[dict[str, object]]:
        """Parse LLM JSON response with fallbacks for common issues.

        Handles: extra data after JSON array, invalid escape sequences,
        and multiple concatenated JSON arrays.

        Args:
            text: Raw JSON text from LLM response.

        Returns:
            Parsed list of entry dicts.

        Raises:
            LlmProcessingError: If no valid JSON can be extracted.
        """
        for candidate in json_candidates(text):
            result = try_parse_json_array(candidate)
            if result is not None:
                return result

        msg = f"Failed to parse LLM response as JSON after all fallbacks: {text[:200]}"
        raise LlmProcessingError(msg)

    @staticmethod
    def _assign_neutral_scores(batch: list[Story], result: LlmPhaseResult) -> None:
        """Assign neutral score to all stories in a failed batch.

        Args:
            batch: Stories that failed evaluation.
            result: Accumulated phase result (mutated in place).
        """
        for story in batch:
            if story.story_id not in result.scores:
                result.scores[story.story_id] = _NEUTRAL_SCORE
                result.stories_evaluated += 1


def _clamp_score(value: object) -> float:
    """Clamp a value to the [0.0, 1.0] range.

    Args:
        value: Raw score value from LLM response.

    Returns:
        Float clamped between 0.0 and 1.0.
    """
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _NEUTRAL_SCORE
    return max(0.0, min(1.0, score))
