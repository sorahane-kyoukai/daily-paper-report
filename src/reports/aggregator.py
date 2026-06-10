"""Aggregate saved day archives into weekly and monthly paper reports."""

from __future__ import annotations

import json
import re
import zoneinfo
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from src.reports.models import (
    ReportDigest,
    ReportIndex,
    ReportIndexEntry,
    ReportMetadata,
    ReportType,
)


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")
MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")
PAPER_LINK_TYPES = {"arxiv", "paper", "openreview"}
REPORT_SECTION_NAMES = ("papers", "top5", "radar")
DECEMBER = 12
CATEGORY_LABELS = {
    "cs.AI": "AI 方法",
    "cs.CL": "自然語言處理",
    "cs.CV": "電腦視覺",
    "cs.LG": "機器學習",
    "cs.RO": "機器人",
    "cs.CR": "安全與可靠性",
    "stat.ML": "統計機器學習",
}
ReportMetadataGenerator = Callable[[ReportDigest], ReportMetadata | None]


@dataclass(frozen=True)
class PeriodRange:
    """Inclusive local-date range for one report period."""

    report_type: ReportType
    period_id: str
    start_date: date
    end_date: date


def build_report_from_archives(  # noqa: PLR0913
    output_dir: Path,
    report_type: ReportType,
    target_date: date,
    timezone: str,
    limit: int = 100,
    period_id: str | None = None,
    previous_month: bool = False,
    archive_lookahead_days: int = 1,
    metadata_generator: ReportMetadataGenerator | None = None,
) -> ReportDigest:
    """Build and write a report from saved day archive JSON files.

    Args:
        output_dir: Site output directory containing api/day/*.json.
        report_type: Weekly or monthly report type.
        target_date: Local date used when period_id is omitted.
        timezone: IANA timezone name for publication-date bucketing.
        limit: Maximum number of recommended papers to keep.
        period_id: Optional explicit period id, YYYY-Www or YYYY-MM.
        previous_month: For monthly reports without period_id, use the month
            before target_date. This matches CI runs on the first day of a month.
        archive_lookahead_days: Extra archive dates after the period end to scan
            for late-arriving papers whose published_at still belongs to the
            report period.
        metadata_generator: Optional callable that can replace the fallback title
            and summary after recommendations are selected.

    Returns:
        The generated report digest.
    """
    if archive_lookahead_days < 0:
        raise ValueError("archive_lookahead_days must be greater than or equal to 0")

    local_tz = zoneinfo.ZoneInfo(timezone)
    period = resolve_period(
        report_type=report_type,
        target_date=target_date,
        period_id=period_id,
        previous_month=previous_month,
    )

    api_day_dir = output_dir / "api" / "day"
    archive_files = _collect_archive_files(api_day_dir)
    period_dates = list(_iter_dates(period.start_date, period.end_date))
    scan_dates = list(period_dates)
    scan_dates.extend(
        period.end_date + timedelta(days=offset)
        for offset in range(1, archive_lookahead_days + 1)
    )
    covered_dates = [day.isoformat() for day in period_dates if day in archive_files]
    missing_dates = [
        day.isoformat() for day in period_dates if day not in archive_files
    ]

    candidates: list[dict[str, Any]] = []
    source_files: list[str] = []
    items_considered = 0

    for archive_date in scan_dates:
        archive_path = archive_files.get(archive_date)
        if archive_path is None:
            continue
        day_text = archive_date.isoformat()
        source_files.append(f"api/day/{archive_path.name}")
        daily_payload = _load_json_object(archive_path)
        day_candidates = _collect_paper_candidates(daily_payload)
        items_considered += len(day_candidates)

        for story in day_candidates:
            story_date = _story_local_date(story, archive_date, local_tz)
            if period.start_date <= story_date <= period.end_date:
                story["published_local_date"] = story_date.isoformat()
                story["report_source_date"] = day_text
                candidates.append(story)

    ranked_stories = _rank_unique_stories(candidates, local_tz)
    recommendations = ranked_stories[:limit]
    for index, story in enumerate(recommendations, start=1):
        story["report_rank"] = index
        story["report_score"] = round(_report_score(story), 6)

    report = ReportDigest(
        report_type=report_type,
        period_id=period.period_id,
        title=_build_title(period),
        summary=_build_summary(
            period=period,
            recommendations=recommendations,
            covered_dates=covered_dates,
            missing_dates=missing_dates,
            stories_considered=len(ranked_stories),
        ),
        timezone=timezone,
        period_start=period.start_date.isoformat(),
        period_end=period.end_date.isoformat(),
        generated_at=datetime.now(UTC).isoformat(),
        covered_dates=covered_dates,
        missing_dates=missing_dates,
        source_files=source_files,
        items_considered=items_considered,
        stories_considered=len(ranked_stories),
        recommendations=recommendations,
        selection_policy={
            "limit": limit,
            "archive_lookahead_days": archive_lookahead_days,
            "source_sections": list(REPORT_SECTION_NAMES),
            "dedupe_keys": ["arxiv_id", "story_id", "primary_link.url"],
            "ranking": (
                "score.total_score descending, then publication time descending; "
                "paper-like stories are pulled from daily papers, top5, and radar"
            ),
            "period_source": "explicit period_id"
            if period_id
            else "target_date and report_type",
            "metadata_source": "fallback",
        },
    )

    report = _apply_generated_metadata(report, metadata_generator)
    _write_report(output_dir, report)
    _update_report_index(output_dir, report)
    return report


def resolve_period(
    report_type: ReportType,
    target_date: date,
    period_id: str | None = None,
    previous_month: bool = False,
) -> PeriodRange:
    """Resolve report type and target date into an inclusive period range."""
    if period_id:
        return _parse_period_id(report_type, period_id)

    if report_type == "weekly":
        start_date = target_date - timedelta(days=target_date.weekday())
        end_date = start_date + timedelta(days=6)
        iso_year, iso_week, _ = target_date.isocalendar()
        return PeriodRange(
            report_type=report_type,
            period_id=f"{iso_year}-W{iso_week:02d}",
            start_date=start_date,
            end_date=end_date,
        )

    month_anchor = target_date
    if previous_month:
        month_anchor = target_date.replace(day=1) - timedelta(days=1)

    start_date = month_anchor.replace(day=1)
    end_date = _month_end(start_date)
    return PeriodRange(
        report_type=report_type,
        period_id=start_date.strftime("%Y-%m"),
        start_date=start_date,
        end_date=end_date,
    )


def _parse_period_id(report_type: ReportType, period_id: str) -> PeriodRange:
    if report_type == "weekly":
        match = WEEK_RE.match(period_id)
        if not match:
            raise ValueError("weekly period_id must use YYYY-Www format")
        start_date = date.fromisocalendar(
            int(match.group("year")), int(match.group("week")), 1
        )
        return PeriodRange(
            report_type=report_type,
            period_id=period_id,
            start_date=start_date,
            end_date=start_date + timedelta(days=6),
        )

    match = MONTH_RE.match(period_id)
    if not match:
        raise ValueError("monthly period_id must use YYYY-MM format")
    year = int(match.group("year"))
    month = int(match.group("month"))
    start_date = date(year, month, 1)
    return PeriodRange(
        report_type=report_type,
        period_id=period_id,
        start_date=start_date,
        end_date=_month_end(start_date),
    )


def _collect_archive_files(api_day_dir: Path) -> dict[date, Path]:
    if not api_day_dir.exists():
        return {}

    archives: dict[date, Path] = {}
    for path in api_day_dir.glob("*.json"):
        if not DATE_RE.match(path.stem):
            continue
        archives[date.fromisoformat(path.stem)] = path
    return archives


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise TypeError(f"Archive JSON must be an object: {path}")
    return cast("dict[str, Any]", data)


def _collect_paper_candidates(daily_payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for section_name in REPORT_SECTION_NAMES:
        section = daily_payload.get(section_name, [])
        if not isinstance(section, list):
            continue

        for item in section:
            if not isinstance(item, dict):
                continue
            story = dict(item)
            if not _is_paper_story(story):
                continue
            story["report_source_section"] = section_name
            candidates.append(story)

    return candidates


def _is_paper_story(story: dict[str, Any]) -> bool:
    if story.get("arxiv_id"):
        return True

    primary_link = story.get("primary_link", {})
    if isinstance(primary_link, dict):
        link_type = str(primary_link.get("link_type", "")).lower()
        source_id = str(primary_link.get("source_id", "")).lower()
        if link_type in PAPER_LINK_TYPES:
            return True
        if source_id.startswith("arxiv-") or source_id == "hf-daily-papers":
            return True

    categories = story.get("categories", [])
    if isinstance(categories, list):
        return any(
            isinstance(category, str) and category.startswith(("cs.", "stat."))
            for category in categories
        )

    return False


def _story_local_date(
    story: dict[str, Any], fallback_date: date, timezone: zoneinfo.ZoneInfo
) -> date:
    published_at = story.get("published_at")
    if not isinstance(published_at, str) or not published_at:
        return fallback_date

    parsed = _parse_datetime(published_at)
    if parsed is None:
        return fallback_date
    return parsed.astimezone(timezone).date()


def _rank_unique_stories(
    candidates: list[dict[str, Any]], timezone: zoneinfo.ZoneInfo
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}

    for story in candidates:
        key = _story_key(story)
        previous = unique.get(key)
        if previous is None or _report_score(story) > _report_score(previous):
            unique[key] = story

    return sorted(
        unique.values(),
        key=lambda story: (
            -_report_score(story),
            -_published_timestamp(story, timezone),
            str(story.get("title", "")).lower(),
        ),
    )


def _story_key(story: dict[str, Any]) -> str:
    for field_name in ("arxiv_id", "story_id"):
        value = story.get(field_name)
        if isinstance(value, str) and value:
            return f"{field_name}:{value.lower()}"

    primary_link = story.get("primary_link", {})
    if isinstance(primary_link, dict):
        url = primary_link.get("url")
        if isinstance(url, str) and url:
            return f"url:{url.lower()}"

    title = str(story.get("title", "")).strip().lower()
    published_at = str(story.get("published_at", "")).strip()
    return f"title:{title}:{published_at}"


def _report_score(story: dict[str, Any]) -> float:
    scores = story.get("scores", {})
    if isinstance(scores, dict):
        total_score = scores.get("total_score", 0)
        if isinstance(total_score, int | float):
            return float(total_score)
    return 0.0


def _published_timestamp(story: dict[str, Any], timezone: zoneinfo.ZoneInfo) -> float:
    published_at = story.get("published_at")
    if not isinstance(published_at, str):
        return 0.0
    parsed = _parse_datetime(published_at)
    if parsed is None:
        local_date = story.get("published_local_date")
        if isinstance(local_date, str) and DATE_RE.match(local_date):
            return (
                datetime.fromisoformat(local_date).replace(tzinfo=timezone).timestamp()
            )
        return 0.0
    return parsed.timestamp()


def _parse_datetime(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _write_report(output_dir: Path, report: ReportDigest) -> Path:
    report_path = (
        output_dir / "api" / "reports" / report.report_type / f"{report.period_id}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return report_path


def _update_report_index(output_dir: Path, report: ReportDigest) -> None:
    index_path = output_dir / "api" / "reports" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    if index_path.exists():
        index = ReportIndex.model_validate(json.loads(index_path.read_text()))
    else:
        index = ReportIndex(generated_at=datetime.now(UTC).isoformat())

    report_path = f"api/reports/{report.report_type}/{report.period_id}.json"
    entry = ReportIndexEntry(
        report_type=report.report_type,
        period_id=report.period_id,
        title=report.title,
        summary=report.summary,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        path=report_path,
        recommendation_count=len(report.recommendations),
        missing_dates=report.missing_dates,
    )

    weekly = list(index.weekly)
    monthly = list(index.monthly)
    target_entries = weekly if report.report_type == "weekly" else monthly
    target_entries[:] = [
        existing
        for existing in target_entries
        if existing.period_id != report.period_id
    ]
    target_entries.append(entry)
    target_entries.sort(key=lambda item: item.period_start, reverse=True)

    latest = dict(index.latest)
    latest["weekly"] = weekly[0].period_id if weekly else None
    latest["monthly"] = monthly[0].period_id if monthly else None

    updated = ReportIndex(
        generated_at=datetime.now(UTC).isoformat(),
        latest=latest,
        weekly=weekly,
        monthly=monthly,
    )
    index_path.write_text(
        json.dumps(
            updated.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _build_title(period: PeriodRange) -> str:
    if period.report_type == "weekly":
        return f"{period.period_id} AI 論文週報"
    return f"{period.period_id} AI 論文月報"


def _build_summary(
    *,
    period: PeriodRange,
    recommendations: list[dict[str, Any]],
    covered_dates: list[str],
    missing_dates: list[str],
    stories_considered: int,
) -> str:
    report_label = (
        "本週" if period.report_type == "weekly" else f"{period.period_id} 月"
    )
    coverage = f"涵蓋 {len(covered_dates)} 天資料"
    if missing_dates:
        coverage += f"，另有 {len(missing_dates)} 天缺資料"
    else:
        coverage += "，資料完整"

    if not recommendations:
        return f"{report_label}尚未找到符合條件的論文推薦。{coverage}。"

    category_text = _top_category_text(recommendations)
    topic_clause = f"，重點集中在 {category_text}" if category_text else ""
    return (
        f"{report_label}整理 {len(recommendations)} 篇值得看的 AI 論文{topic_clause}。"
        f"{coverage}，共從 {stories_considered} 篇候選中篩選。"
    )


def _top_category_text(recommendations: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for story in recommendations:
        categories = story.get("categories", [])
        if not isinstance(categories, list):
            continue
        for category in categories:
            if not isinstance(category, str) or not category:
                continue
            label = CATEGORY_LABELS.get(category, category)
            counts[label] = counts.get(label, 0) + 1

    top_categories = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    return "、".join(label for label, _count in top_categories)


def _apply_generated_metadata(
    report: ReportDigest,
    metadata_generator: ReportMetadataGenerator | None,
) -> ReportDigest:
    if metadata_generator is None:
        return report

    metadata = metadata_generator(report)
    if metadata is None:
        return report

    updates: dict[str, Any] = {}
    title = _clean_metadata_text(metadata.title)
    summary = _clean_metadata_text(metadata.summary)
    if title:
        updates["title"] = title
    if summary:
        updates["summary"] = summary
    if not updates:
        return report

    updates["selection_policy"] = {
        **report.selection_policy,
        "metadata_source": metadata.source,
    }
    return report.model_copy(update=updates)


def _clean_metadata_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _month_end(month_start: date) -> date:
    if month_start.month == DECEMBER:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    return next_month - timedelta(days=1)


def _iter_dates(start_date: date, end_date: date) -> list[date]:
    days = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]
