"""AI-generated editorial metadata for weekly and monthly reports."""

from __future__ import annotations

import json
import re
from typing import Any, cast

from src.features.llm.json_utils import fix_escape_sequences, strip_markdown_fences
from src.features.llm.protocols import LlmClient
from src.reports.models import ReportDigest, ReportMetadata


MAX_PROMPT_STORIES = 16
MAX_TITLE_CHARS = 34
MAX_SUMMARY_CHARS = 180
MIN_SENTENCE_TRUNCATE_CHARS = 50

SYSTEM_INSTRUCTION = """你是專業的 AI 研究編輯。請根據候選論文與技術文章內容，為週報或月報產生繁體中文標題與快速總結。只輸出 JSON object，不要使用 Markdown。"""


def generate_report_metadata(
    client: LlmClient,
    report: ReportDigest,
) -> ReportMetadata | None:
    """Generate a concise title and quick summary for a report."""
    raw_response = client.generate_content(
        _build_prompt(report),
        system_instruction=SYSTEM_INSTRUCTION,
    )
    parsed = _try_parse_json_object(raw_response)
    if parsed is None:
        return None

    title = _sanitize_title(
        _first_string(parsed, "title", "title_zh", "headline", "headline_zh")
    )
    summary = _sanitize_summary(
        _first_string(parsed, "summary", "summary_zh", "quick_summary")
    )
    if not title and not summary:
        return None

    return ReportMetadata(title=title, summary=summary, source="ai")


def _build_prompt(report: ReportDigest) -> str:
    payload = {
        "report_type": report.report_type,
        "period_id": report.period_id,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "recommendation_count": len(report.recommendations),
        "blog_recommendation_count": len(report.blog_recommendations),
        "covered_dates": report.covered_dates,
        "missing_date_count": len(report.missing_dates),
        "top_papers": [
            _story_prompt_payload(story)
            for story in report.recommendations[:MAX_PROMPT_STORIES]
        ],
        "top_blog_articles": [
            _story_prompt_payload(story)
            for story in report.blog_recommendations[:MAX_PROMPT_STORIES]
        ],
    }

    return (
        "請為以下 AI 研究與技術文章"
        f"{'週報' if report.report_type == 'weekly' else '月報'}"
        "產生可直接顯示在網站上的 metadata。\n"
        "規則：\n"
        "- title 必須包含「週報」或「月報」，專業、克制，不要誇張或像廣告。\n"
        f"- title 最多 {MAX_TITLE_CHARS} 個中文字元，避免重複日期。\n"
        f"- summary 用 1 到 2 句快速總結，最多 {MAX_SUMMARY_CHARS} 個中文字元。\n"
        "- summary 要概括主要研究方向、值得看的文章脈絡與挑選理由，不要逐篇列舉。\n"
        '- 只回傳 JSON：{"title":"...","summary":"..."}\n\n'
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _story_prompt_payload(story: dict[str, Any]) -> dict[str, object]:
    title = _string_value(story.get("title_zh")) or _string_value(story.get("title"))
    summary = _string_value(story.get("summary_zh")) or _string_value(
        story.get("summary")
    )
    return {
        "rank": story.get("report_rank"),
        "title": title,
        "summary": _truncate_text(summary, 260),
        "categories": story.get("categories", []),
        "score": story.get("report_score"),
    }


def _try_parse_json_object(text: str) -> dict[str, object] | None:
    candidates = [strip_markdown_fences(text)]
    extracted = _extract_first_json_object(candidates[0])
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for candidate in candidates:
        for attempt in (candidate, fix_escape_sequences(candidate)):
            try:
                parsed = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return cast("dict[str, object]", parsed)
    return None


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _first_string(data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        text = _string_value(value)
        if text:
            return text
    return None


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _sanitize_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip(" `\"'「」")
    cleaned = cleaned.rstrip("。.!！")
    return _truncate_text(cleaned, MAX_TITLE_CHARS)


def _sanitize_summary(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip(" `\"'")
    return _truncate_text(cleaned, MAX_SUMMARY_CHARS, prefer_sentence=True)


def _truncate_text(
    text: str | None,
    max_chars: int,
    *,
    prefer_sentence: bool = False,
) -> str | None:
    if not text:
        return None

    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned

    if prefer_sentence:
        sentence = _truncate_at_sentence(cleaned, max_chars)
        if sentence:
            return sentence

    return cleaned[: max_chars - 1].rstrip("，、；：,. ") + "…"


def _truncate_at_sentence(text: str, max_chars: int) -> str | None:
    candidate = text[: max_chars + 1]
    last_index = max(
        candidate.rfind("。"),
        candidate.rfind("！"),
        candidate.rfind("？"),
        candidate.rfind("."),
    )
    if last_index >= MIN_SENTENCE_TRUNCATE_CHARS:
        return text[: last_index + 1].strip()
    return None
