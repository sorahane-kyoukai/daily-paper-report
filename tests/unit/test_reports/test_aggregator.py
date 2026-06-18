"""Tests for weekly and monthly report aggregation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.reports.aggregator import build_report_from_archives, resolve_period
from src.reports.models import ReportDigest, ReportMetadata


def _story(
    story_id: str,
    score: float,
    published_at: str,
    title: str | None = None,
    arxiv_id: str | None = None,
) -> dict[str, object]:
    return {
        "story_id": story_id,
        "title": title or f"Paper {story_id}",
        "title_zh": f"論文 {story_id}",
        "summary": f"Summary for {story_id}",
        "summary_zh": f"這是 {story_id} 的較長繁體中文摘要。",
        "published_at": published_at,
        "authors": ["Ada Lovelace"],
        "categories": ["cs.LG"],
        "arxiv_id": arxiv_id,
        "primary_link": {
            "url": f"https://arxiv.org/abs/{story_id}",
            "link_type": "arxiv",
            "source_id": "arxiv-cs-lg",
            "tier": 0,
            "title": title or f"Paper {story_id}",
        },
        "links": [],
        "entities": [],
        "scores": {
            "total_score": score,
            "tier_score": 5,
            "kind_score": 3,
            "topic_score": 1,
            "recency_score": 1,
            "entity_score": 0,
            "citation_score": 0,
            "cross_source_score": 0,
            "semantic_score": 0,
            "llm_relevance_score": 0,
        },
    }


def _write_day(output_dir: Path, day: str, payload: dict[str, object]) -> None:
    day_dir = output_dir / "api" / "day"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"{day}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2)
    )


def test_resolve_weekly_period_uses_monday_to_sunday() -> None:
    period = resolve_period("weekly", date(2026, 5, 24))

    assert period.period_id == "2026-W21"
    assert period.start_date == date(2026, 5, 18)
    assert period.end_date == date(2026, 5, 24)


def test_monthly_previous_month_uses_month_before_target() -> None:
    period = resolve_period("monthly", date(2026, 6, 1), previous_month=True)

    assert period.period_id == "2026-05"
    assert period.start_date == date(2026, 5, 1)
    assert period.end_date == date(2026, 5, 31)


def test_build_weekly_report_dedupes_and_writes_index(tmp_path: Path) -> None:
    _write_day(
        tmp_path,
        "2026-05-18",
        {
            "papers": [
                _story(
                    "paper-a",
                    7,
                    "2026-05-18T08:00:00+00:00",
                    arxiv_id="2505.00001",
                ),
                _story("2505.00002", 12, "2026-05-18T09:00:00+00:00"),
            ],
            "top5": [
                _story(
                    "duplicate",
                    15,
                    "2026-05-18T10:00:00+00:00",
                    arxiv_id="2505.00001",
                )
            ],
            "radar": [{"story_id": "blog", "primary_link": {"link_type": "blog"}}],
        },
    )
    _write_day(
        tmp_path,
        "2026-05-19",
        {
            "papers": [
                _story("2505.00003", 9, "2026-05-19T08:00:00+00:00"),
            ],
            "top5": [],
            "radar": [],
        },
    )

    report = build_report_from_archives(
        output_dir=tmp_path,
        report_type="weekly",
        target_date=date(2026, 5, 24),
        timezone="Asia/Taipei",
        limit=2,
    )

    assert report.period_id == "2026-W21"
    assert report.title == "2026-W21 AI 論文週報"
    assert report.summary is not None
    assert "2 篇值得看的 AI 論文" in report.summary
    assert report.covered_dates == ["2026-05-18", "2026-05-19"]
    assert "2026-05-20" in report.missing_dates
    assert report.items_considered == 4
    assert report.stories_considered == 3
    assert [story["report_rank"] for story in report.recommendations] == [1, 2]
    assert report.recommendations[0]["arxiv_id"] == "2505.00001"
    assert report.recommendations[0]["report_source_section"] == "top5"

    report_path = tmp_path / "api" / "reports" / "weekly" / "2026-W21.json"
    index_path = tmp_path / "api" / "reports" / "index.json"
    assert report_path.is_file()
    assert index_path.is_file()

    index_data = json.loads(index_path.read_text())
    assert index_data["latest"]["weekly"] == "2026-W21"
    assert index_data["weekly"][0]["summary"] == report.summary
    assert index_data["weekly"][0]["recommendation_count"] == 2
    assert index_data["weekly"][0]["title"] == report.title


def test_build_weekly_report_updates_legacy_index_without_paths(tmp_path: Path) -> None:
    index_path = tmp_path / "api" / "reports" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-17T00:00:00Z",
                "latest": {"weekly": "2026-W20", "monthly": None},
                "weekly": [
                    {
                        "period_id": "2026-W20",
                        "title": "Legacy weekly report",
                        "summary": "Legacy summary",
                        "period_start": "2026-05-11",
                        "period_end": "2026-05-17",
                        "generated_at": "2026-05-17T00:00:00Z",
                        "recommendation_count": 1,
                        "missing_dates": [],
                    }
                ],
                "monthly": [],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    _write_day(
        tmp_path,
        "2026-05-18",
        {
            "papers": [_story("new-paper", 10, "2026-05-18T08:00:00+00:00")],
            "top5": [],
            "radar": [],
        },
    )

    report = build_report_from_archives(
        output_dir=tmp_path,
        report_type="weekly",
        target_date=date(2026, 5, 24),
        timezone="Asia/Taipei",
    )

    index_data = json.loads(index_path.read_text())
    legacy_entry = next(
        entry for entry in index_data["weekly"] if entry["period_id"] == "2026-W20"
    )
    assert index_data["latest"]["weekly"] == report.period_id
    assert legacy_entry["report_type"] == "weekly"
    assert legacy_entry["path"] == "api/reports/weekly/2026-W20.json"


def test_build_monthly_report_filters_to_period(tmp_path: Path) -> None:
    _write_day(
        tmp_path,
        "2026-05-31",
        {
            "papers": [
                _story("may-paper", 10, "2026-05-31T08:00:00+00:00"),
                _story("june-paper", 99, "2026-06-01T08:00:00+00:00"),
            ],
            "top5": [],
            "radar": [],
        },
    )

    report = build_report_from_archives(
        output_dir=tmp_path,
        report_type="monthly",
        target_date=date(2026, 6, 1),
        timezone="Asia/Taipei",
        previous_month=True,
    )

    assert report.period_id == "2026-05"
    assert [story["story_id"] for story in report.recommendations] == ["may-paper"]
    assert (tmp_path / "api" / "reports" / "monthly" / "2026-05.json").is_file()


def test_monthly_report_scans_next_day_archive_for_late_month_papers(
    tmp_path: Path,
) -> None:
    _write_day(
        tmp_path,
        "2026-06-01",
        {
            "papers": [
                _story("late-may-paper", 15, "2026-05-31T23:20:00+08:00"),
                _story("june-paper", 99, "2026-06-01T09:00:00+08:00"),
            ],
            "top5": [],
            "radar": [],
        },
    )

    report = build_report_from_archives(
        output_dir=tmp_path,
        report_type="monthly",
        target_date=date(2026, 6, 1),
        timezone="Asia/Taipei",
        previous_month=True,
    )

    assert report.period_id == "2026-05"
    assert report.covered_dates == []
    assert "2026-05-31" in report.missing_dates
    assert report.source_files == ["api/day/2026-06-01.json"]
    assert [story["story_id"] for story in report.recommendations] == ["late-may-paper"]
    assert report.selection_policy["archive_lookahead_days"] == 1


def test_report_metadata_generator_replaces_title_and_summary(
    tmp_path: Path,
) -> None:
    _write_day(
        tmp_path,
        "2026-05-18",
        {
            "papers": [
                _story("agent-paper", 10, "2026-05-18T08:00:00+00:00"),
            ],
            "top5": [],
            "radar": [],
        },
    )

    def _metadata_generator(report: ReportDigest) -> ReportMetadata:
        assert report.summary
        assert report.selection_policy["metadata_source"] == "fallback"
        return ReportMetadata(
            title="AI 週報：代理與多模態進展",
            summary="本週重點聚焦代理系統與多模態模型，推薦優先看方法完整且影響面較廣的研究。",
        )

    report = build_report_from_archives(
        output_dir=tmp_path,
        report_type="weekly",
        target_date=date(2026, 5, 24),
        timezone="Asia/Taipei",
        metadata_generator=_metadata_generator,
    )

    assert report.title == "AI 週報：代理與多模態進展"
    assert (
        report.summary
        == "本週重點聚焦代理系統與多模態模型，推薦優先看方法完整且影響面較廣的研究。"
    )
    assert report.selection_policy["metadata_source"] == "ai"

    index_data = json.loads((tmp_path / "api" / "reports" / "index.json").read_text())
    assert index_data["weekly"][0]["title"] == report.title
    assert index_data["weekly"][0]["summary"] == report.summary
