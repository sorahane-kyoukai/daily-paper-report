"""Tests for AI-generated report metadata parsing."""

from __future__ import annotations

from src.reports.ai_metadata import generate_report_metadata
from src.reports.models import ReportDigest


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""
        self.system_instruction: str | None = None

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        self.prompt = prompt
        self.system_instruction = system_instruction
        return self.response


def test_generate_report_metadata_parses_json_object() -> None:
    client = FakeLlmClient(
        '```json\n{"title":"AI 週報：推理與代理進展。","summary":"本週重點集中在推理模型與代理系統，適合快速掌握高分研究。"}\n```'
    )

    metadata = generate_report_metadata(client, _report())

    assert metadata is not None
    assert metadata.source == "ai"
    assert metadata.title == "AI 週報：推理與代理進展"
    assert (
        metadata.summary == "本週重點集中在推理模型與代理系統，適合快速掌握高分研究。"
    )
    assert "top_papers" in client.prompt
    assert "top_blog_articles" in client.prompt


def test_generate_report_metadata_returns_none_for_invalid_response() -> None:
    metadata = generate_report_metadata(FakeLlmClient("not json"), _report())

    assert metadata is None


def _report() -> ReportDigest:
    return ReportDigest(
        report_type="weekly",
        period_id="2026-W21",
        title="2026-W21 AI 論文週報",
        summary="本週整理 1 篇值得看的 AI 論文。",
        timezone="Asia/Taipei",
        period_start="2026-05-18",
        period_end="2026-05-24",
        generated_at="2026-05-24T00:00:00+00:00",
        covered_dates=["2026-05-18"],
        missing_dates=[],
        source_files=["api/day/2026-05-18.json"],
        items_considered=1,
        stories_considered=1,
        recommendations=[
            {
                "story_id": "paper-a",
                "title": "Reasoning Agents",
                "summary": "A paper about reasoning agents.",
                "categories": ["cs.AI"],
                "report_rank": 1,
                "report_score": 10,
            }
        ],
        selection_policy={"metadata_source": "fallback"},
    )
