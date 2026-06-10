#!/usr/bin/env python3
"""Re-translate all paper summaries using DeepSeek API with sufficient token budget.

This script reads all day archive JSON files, collects unique stories, and
re-translates every title and summary to Traditional Chinese using DeepSeek.
It overwrites the existing translations_zh.json cache.

Usage:
    # Set the API key via environment variable (or pass via --api-key)
    export DEEPSEEK_API_KEY="sk-..."

    # Re-translate everything
    python scripts/retranslate.py --out public

    # Re-translate only a specific date range
    python scripts/retranslate.py --out public --date-from 2026-05-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx


# ── DeepSeek API settings ──────────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # Latest DeepSeek chat model
MAX_TOKENS = 8192  # Enough for batch stories x 400 chars Chinese + JSON
BATCH_SIZE = 5  # Keep small to avoid JSON truncation from token limits
MIN_REQUEST_INTERVAL = 0.5  # seconds
MIN_REQUEST_INTERVAL = 1.0  # seconds
MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0

SYSTEM_INSTRUCTION = (
    "You are a professional translator specializing in AI/ML academic papers. "
    "Translate to Traditional Chinese (繁體中文). "
    "Preserve technical terms, model names, acronyms, and proper nouns in English. "
    "For example: 'Transformer', 'GPT-4', 'RLHF', 'fine-tuning' should remain in English. "
    "Maintain the academic tone and precision of the original text. "
    "Respond ONLY with a JSON array, no markdown fences or extra text."
)

_BATCH_TEMPLATE = """## Stories to Translate

{stories_section}

## Output Format
Respond with a JSON array. Each element must have these fields:
- "id": the story_id exactly as given
- "title_zh": the title translated to Traditional Chinese
- "summary_zh": a complete Traditional Chinese summary, 3-5 full sentences and about 250-400 Chinese characters when the source summary has enough information (empty string if no summary)

CRITICAL: Every summary_zh MUST end with proper punctuation (。！？) — never truncate mid-sentence.
Keep technical terms, model names, acronyms, and proper nouns in English within the Chinese text.
Use Chinese full stops "。" between sentences so the frontend can display readable paragraphs.
Do not translate the full abstract verbatim; explain the key problem, method, result or claimed benefit, and why it may matter.

Example:
[{{"id": "example-1", "title_zh": "基於 Transformer 的新型多模態學習架構", "summary_zh": "本文聚焦多模態資料在訓練與推論時的表徵對齊問題，提出了結合 Transformer 與 contrastive learning 的新架構。作者強調此方法能降低跨模態噪音，並在多個視覺語言任務上改善準確率。值得關注的是，它也提供了可擴展的消融設計，便於比較不同模態對最終表現的貢獻。"}}]
"""


def build_translation_prompt(stories: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for i, story in enumerate(stories, 1):
        story_id = story["story_id"]
        title = story.get("title", "")
        summary = story.get("summary", "") or ""
        summary_part = f"\n   Summary: {summary}" if summary else ""
        lines.append(f"{i}. [{story_id}] Title: {title}{summary_part}")
    return _BATCH_TEMPLATE.format(stories_section="\n".join(lines))


def chat_completion(
    api_key: str,
    prompt: str,
    *,
    model: str = DEEPSEEK_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Send a chat completion request to DeepSeek with retries."""
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": max_tokens,
    }

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=120.0,
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2**attempt)
                print(
                    f"  Network error (attempt {attempt + 1}), retrying in {delay:.0f}s: {exc}"
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code == 200:
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("No choices in API response")
            content = choices[0].get("message", {}).get("content", "")
            return str(content)

        if response.status_code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
            delay = RETRY_BASE_DELAY * (2**attempt)
            print(
                f"  HTTP {response.status_code} (attempt {attempt + 1}), retrying in {delay:.0f}s"
            )
            time.sleep(delay)
            last_exc = RuntimeError(f"DeepSeek API returned {response.status_code}")
            continue

        raise RuntimeError(
            f"DeepSeek API returned {response.status_code}: {response.text[:300]}"
        )

    raise last_exc or RuntimeError("All retries exhausted")


def parse_response(raw: str, batch: list[dict[str, str]]) -> list[dict[str, str]]:
    """Parse the LLM JSON response into translation entries."""
    import re

    # Strip markdown fences
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)

    # Find JSON array
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON array from text
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                print(f"  Failed to parse response: {text[:200]}...")
                return []
        else:
            print(f"  No JSON array found in response: {text[:200]}...")
            return []

    if not isinstance(parsed, list):
        return []

    valid_ids = {s["story_id"] for s in batch}
    results: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("id", "")).strip()
        # Handle bracket-wrapped IDs
        if raw_id.startswith("[") and raw_id.endswith("]"):
            raw_id = raw_id[1:-1].strip()
        # Handle numeric IDs (1-based index)
        if raw_id.isdigit():
            idx = int(raw_id) - 1
            if 0 <= idx < len(batch):
                raw_id = batch[idx]["story_id"]
        if raw_id not in valid_ids:
            continue
        title_zh = str(item.get("title_zh", "")).strip()
        summary_zh = str(item.get("summary_zh", "")).strip()
        if not title_zh:
            continue
        results.append(
            {
                "story_id": raw_id,
                "title_zh": title_zh,
                "summary_zh": summary_zh,
            }
        )

    return results


def collect_stories(
    api_day_dir: Path, date_from: str | None = None
) -> dict[str, dict[str, str]]:
    """Collect all unique stories from day archive JSON files.

    Returns a dict mapping story_id -> {story_id, title, summary}.
    """
    stories: dict[str, dict[str, str]] = {}
    json_files = sorted(api_day_dir.glob("*.json"))

    for json_path in json_files:
        if date_from and json_path.stem < date_from:
            continue
        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError):
            print(f"  Skipping unreadable: {json_path.name}")
            continue

        for section in ("papers", "top5", "radar"):
            for item in data.get(section, []):
                if not isinstance(item, dict):
                    continue
                sid = item.get("story_id")
                if not sid or sid in stories:
                    continue
                # Only translate paper-like stories (have arxiv_id or summary)
                title = str(item.get("title", "")).strip()
                summary = str(item.get("summary", "")).strip()
                if not title:
                    continue
                stories[sid] = {
                    "story_id": sid,
                    "title": title,
                    "summary": summary,
                }

    return stories


def load_existing_translations(path: Path) -> dict[str, dict[str, str]]:
    """Load existing translations cache."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return {}


def check_truncated(summary: str) -> bool:
    """Check if a summary appears truncated (doesn't end with punctuation)."""
    if not summary:
        return False
    return not summary.rstrip().endswith(("。", "！", "？", ".", "!", "?", "」"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-translate all paper summaries with DeepSeek"
    )
    parser.add_argument(
        "--out", required=True, type=Path, help="Output directory (e.g., public)"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("DEEPSEEK_API_KEY", ""),
        help="DeepSeek API key (or set DEEPSEEK_API_KEY env var)",
    )
    parser.add_argument(
        "--date-from",
        type=str,
        default=None,
        help="Only retranslate stories from this date onward (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Batch size for translation (default: {BATCH_SIZE})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEEPSEEK_MODEL,
        help=f"DeepSeek model (default: {DEEPSEEK_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making API calls",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("Error: DEEPSEEK_API_KEY not set. Use --api-key or set env var.")
        sys.exit(1)

    api_day_dir = args.out / "api" / "day"
    if not api_day_dir.exists():
        print(f"Error: {api_day_dir} does not exist")
        sys.exit(1)

    translations_path = args.out / "api" / "translations_zh.json"

    # Collect all stories
    print("Collecting stories from day archives...")
    stories = collect_stories(api_day_dir, date_from=args.date_from)
    print(f"  Found {len(stories)} unique stories")

    # Load existing translations
    existing = load_existing_translations(translations_path)
    print(f"  Existing translations: {len(existing)}")

    # Check current truncation status
    truncated_count = sum(
        1 for v in existing.values() if check_truncated(v.get("summary_zh", ""))
    )
    print(f"  Currently truncated: {truncated_count}")

    # Determine which stories need translation
    to_translate = [
        s
        for sid, s in stories.items()
        if sid not in existing or check_truncated(existing[sid].get("summary_zh", ""))
    ]
    print(f"  Stories to re-translate: {len(to_translate)}")

    # Also add stories whose existing translations are truncated but not in day archives
    truncated_existing = {
        sid: v
        for sid, v in existing.items()
        if check_truncated(v.get("summary_zh", ""))
        and sid not in {s["story_id"] for s in to_translate}
    }
    if truncated_existing:
        print(
            f"  Adding {len(truncated_existing)} truncated entries from existing cache"
        )
        to_translate.extend(
            {"story_id": sid, "title": "", "summary": ""} for sid in truncated_existing
        )

    if args.dry_run:
        print("\n[Dry run] Would translate these stories:")
        for s in to_translate[:10]:
            print(f"  - {s['story_id']}: {s['title'][:80]}")
        if len(to_translate) > 10:
            print(f"  ... and {len(to_translate) - 10} more")
        return

    if not to_translate:
        print("Nothing to translate. All summaries look complete.")
        return

    # Load existing as base, then update with new translations
    new_translations = dict(existing)
    success_count = 0
    fail_count = 0

    def process_batch(batch: list[dict[str, str]], depth: int = 0) -> None:
        """Process a batch with adaptive splitting on failure."""
        nonlocal success_count, fail_count

        if not batch:
            return

        story_ids = [s["story_id"] for s in batch]
        indent = "  " * depth
        print(
            f"{indent}Translating {len(batch)} stories: {', '.join(story_ids[:3])}..."
            + (f" (+{len(story_ids) - 3} more)" if len(story_ids) > 3 else "")
        )

        try:
            prompt = build_translation_prompt(batch)
            raw = chat_completion(
                args.api_key,
                prompt,
                model=args.model,
                max_tokens=MAX_TOKENS,
            )
            entries = parse_response(raw, batch)

            for entry in entries:
                sid = entry["story_id"]
                new_translations[sid] = {
                    "story_id": sid,
                    "title_zh": entry["title_zh"],
                    "summary_zh": entry["summary_zh"],
                    "prompt_version": "deepseek-retranslate-v1",
                }
                if check_truncated(entry["summary_zh"]):
                    print(f"{indent}  WARNING: {sid} summary may still be truncated!")
                else:
                    success_count += 1

            missing_ids = set(story_ids) - {e["story_id"] for e in entries}
            if missing_ids:
                missing_stories = [s for s in batch if s["story_id"] in missing_ids]
                if len(missing_stories) == 1:
                    print(f"{indent}  Failed: {missing_ids}")
                    fail_count += 1
                else:
                    print(
                        f"{indent}  Missing {len(missing_stories)}, splitting and retrying..."
                    )
                    mid = max(1, len(missing_stories) // 2)
                    process_batch(missing_stories[:mid], depth + 1)
                    process_batch(missing_stories[mid:], depth + 1)

        except Exception as exc:
            print(f"{indent}  ERROR: {exc}")
            if len(batch) == 1:
                fail_count += 1
            else:
                mid = len(batch) // 2
                process_batch(batch[:mid], depth + 1)
                process_batch(batch[mid:], depth + 1)

    # Build initial batches
    initial_batches = [
        to_translate[i : i + args.batch_size]
        for i in range(0, len(to_translate), args.batch_size)
    ]
    print(
        f"\nTranslating {len(to_translate)} stories in {len(initial_batches)} batches..."
    )

    for batch_idx, batch in enumerate(initial_batches):
        print(f"[{batch_idx + 1}/{len(initial_batches)}]", end=" ")
        process_batch(list(batch))

        # Save incrementally every 5 batches
        if (batch_idx + 1) % 5 == 0 or batch_idx == len(initial_batches) - 1:
            translations_path.parent.mkdir(parents=True, exist_ok=True)
            translations_path.write_text(
                json.dumps(new_translations, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                f"  [Saved {len(new_translations)} translations to {translations_path}]"
            )

        # Rate limiting between batches
        if batch_idx < len(initial_batches) - 1:
            time.sleep(MIN_REQUEST_INTERVAL)

    # Final verification
    final_truncated = sum(
        1 for v in new_translations.values() if check_truncated(v.get("summary_zh", ""))
    )
    print(f"\n{'=' * 60}")
    print(f"Done. {len(new_translations)} total translations.")
    print(f"Successfully re-translated: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Still truncated after re-translation: {final_truncated}")

    if final_truncated > 0:
        print("\nTruncated entries:")
        for sid, v in new_translations.items():
            summary_zh = v.get("summary_zh", "")
            if check_truncated(summary_zh):
                print(f'  {sid}: ends with "{summary_zh[-40:]}"')

    translations_path.write_text(
        json.dumps(new_translations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nFinal translations saved to {translations_path}")


if __name__ == "__main__":
    main()
