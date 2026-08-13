"""Tests for full-paper acquisition, compaction, and cache provenance."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.features.config.schemas.base import LinkType
from src.features.fulltext.models import FullTextDocument, FullTextStatus
from src.features.fulltext.service import FullTextService, _build_document
from src.features.store.models import DateConfidence, Item
from src.linker.models import Story, StoryLink


def _story() -> Story:
    item = Item(
        url="https://arxiv.org/abs/2401.00001",
        source_id="arxiv",
        tier=0,
        kind="paper",
        title="Paper",
        content_hash="hash",
        raw_json=json.dumps({"abstract_snippet": "A useful abstract."}),
        date_confidence=DateConfidence.HIGH,
    )
    link = StoryLink(
        url=item.url,
        link_type=LinkType.ARXIV,
        source_id=item.source_id,
        tier=0,
        title=item.title,
    )
    return Story(
        story_id="arxiv:2401.00001",
        title="Paper",
        primary_link=link,
        links=[link],
        raw_items=[item],
        arxiv_id="2401.00001",
    )


@patch("src.features.fulltext.service.httpx.get")
def test_arxiv_html_is_cached(mock_get: MagicMock, tmp_path: Path) -> None:
    mock_get.return_value = MagicMock(
        content=b"x" * 1000,
        text="<article><h1>Method</h1><p>" + ("evidence " * 200) + "</p></article>",
    )
    mock_get.return_value.raise_for_status.return_value = None
    service = FullTextService(tmp_path)
    first = service.load_for_story(_story())
    second = service.load_for_story(_story())
    assert first.status == FullTextStatus.COMPLETE
    assert first.sha256 == second.sha256
    assert mock_get.call_count == 1


@patch("src.features.fulltext.service.httpx.get")
@patch("src.features.fulltext.service.httpx.stream")
def test_failed_sources_degrade_to_abstract(
    mock_stream: MagicMock, mock_get: MagicMock, tmp_path: Path
) -> None:
    mock_get.side_effect = ValueError("no html")
    mock_stream.side_effect = ValueError("no pdf")
    document = FullTextService(tmp_path).load_for_story(_story())
    assert document.status == FullTextStatus.ABSTRACT_ONLY
    assert document.confidence_multiplier == 0.85
    assert "useful abstract" in document.text


@patch("src.features.fulltext.service.time.sleep")
def test_load_for_stories_throttles_between_fetches(
    mock_sleep: MagicMock, tmp_path: Path
) -> None:
    service = FullTextService(tmp_path)
    document = FullTextDocument(
        story_id="arxiv:2401.00001",
        text="abstract",
        status=FullTextStatus.ABSTRACT_ONLY,
        source_url=None,
        source_format="abstract",
        sha256="hash",
    )
    with patch.object(service, "load_for_story", return_value=document):
        service.load_for_stories([_story(), _story()])
    assert mock_sleep.call_count == 1


def test_oversized_document_is_compacted() -> None:
    document = _build_document(
        "story",
        "method " * 400_000,
        source_url="https://arxiv.org/html/1",
        source_format="html",
        page_count=0,
    )
    assert document.status == FullTextStatus.COMPACTED
    assert len(document.text) < 1_800_000
