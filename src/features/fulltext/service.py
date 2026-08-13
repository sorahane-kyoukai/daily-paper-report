"""Fetch and cache complete paper content without publishing source documents."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from src.features.fulltext.models import FullTextDocument, FullTextStatus
from src.features.llm.deepseek_client import MAX_INPUT_CHARS
from src.linker.models import Story


logger = structlog.get_logger()

_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
_MAX_PAGES = 300
_MAX_PAGE_STREAM_BYTES = 20 * 1024 * 1024
_MIN_USEFUL_CHARS = 800
_HTML_TAGS_TO_DROP = ("script", "style", "nav", "form", "noscript")
_CACHE_RETENTION_SECONDS = 180 * 24 * 60 * 60
# Spacing between fulltext downloads keeps arXiv's per-IP rate limit from being
# tripped by back-to-back HTML/PDF fetches (which previously caused HTTP 429 on
# the next scheduled API collection).
_FULLTEXT_REQUEST_INTERVAL_SECONDS = 3.0


class FullTextService:
    """Resolve full text for paper stories and keep a local content-addressed cache."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = logger.bind(component="fulltext")
        self._prune_expired_cache()

    def _prune_expired_cache(self) -> None:
        """Remove local full-text cache pairs older than 180 days."""
        cutoff = time.time() - _CACHE_RETENTION_SECONDS
        expired_keys: set[str] = set()
        for path in self._cache_dir.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    expired_keys.add(path.stem)
            except OSError:
                continue
        for cache_key in expired_keys:
            for suffix in (".json", ".txt"):
                try:
                    (self._cache_dir / f"{cache_key}{suffix}").unlink(missing_ok=True)
                except OSError:
                    self._log.warning(
                        "fulltext_cache_prune_failed", cache_key=cache_key
                    )
        if expired_keys:
            self._log.info("fulltext_cache_pruned", entries=len(expired_keys))

    def load_for_stories(self, stories: list[Story]) -> dict[str, FullTextDocument]:
        """Fetch documents sequentially to keep Nano memory use bounded.

        A small delay between fetches avoids tripping arXiv's per-IP rate limit
        with back-to-back HTML/PDF downloads, which previously surfaced as HTTP
        429 on the next scheduled API collection.
        """
        documents: dict[str, FullTextDocument] = {}
        last_fetch_at: float | None = None
        for story in stories:
            if not _is_paper(story):
                continue
            if last_fetch_at is not None:
                elapsed = time.monotonic() - last_fetch_at
                if elapsed < _FULLTEXT_REQUEST_INTERVAL_SECONDS:
                    time.sleep(_FULLTEXT_REQUEST_INTERVAL_SECONDS - elapsed)
            documents[story.story_id] = self.load_for_story(story)
            last_fetch_at = time.monotonic()
        return documents

    def load_for_story(self, story: Story) -> FullTextDocument:
        """Return cached or freshly extracted content for one paper."""
        cache_key = hashlib.sha256(story.story_id.encode()).hexdigest()
        cached = self._load_cache(cache_key, story.story_id)
        if cached is not None:
            return cached

        errors: list[str] = []
        candidates = _candidate_urls(story)
        for source_format, url in candidates:
            try:
                if source_format == "html":
                    text, pages = self._extract_html(url)
                else:
                    text, pages = self._extract_pdf(url)
                document = _build_document(
                    story.story_id,
                    text,
                    source_url=url,
                    source_format=source_format,
                    page_count=pages,
                )
                self._save_cache(cache_key, document)
                self._log.info(
                    "fulltext_ready",
                    story_id=story.story_id,
                    status=document.status.value,
                    chars=len(document.text),
                    source_format=source_format,
                )
                return document
            except (
                httpx.HTTPError,
                OSError,
                PdfReadError,
                FileNotDecryptedError,
                ValueError,
            ) as exc:
                errors.append(f"{source_format}:{type(exc).__name__}")
                self._log.warning(
                    "fulltext_candidate_failed",
                    story_id=story.story_id,
                    source_format=source_format,
                    error=type(exc).__name__,
                )

        abstract = _extract_abstract(story)
        document = _build_document(
            story.story_id,
            abstract,
            source_url=None,
            source_format="abstract",
            page_count=0,
            forced_status=FullTextStatus.ABSTRACT_ONLY,
            error=",".join(errors) or "no_fulltext_url",
        )
        self._save_cache(cache_key, document)
        return document

    def _extract_html(self, url: str) -> tuple[str, int]:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=60.0,
            headers={"User-Agent": "daily-paper-report/1.0"},
        )
        response.raise_for_status()
        if len(response.content) > _MAX_DOWNLOAD_BYTES:
            raise ValueError("HTML exceeds download limit")
        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup.find_all(_HTML_TAGS_TO_DROP):
            tag.decompose()
        root = soup.find("article") or soup.find("main") or soup.body
        if root is None:
            raise ValueError("HTML has no document body")
        text = _normalize_text(root.get_text("\n"))
        if len(text) < _MIN_USEFUL_CHARS:
            raise ValueError("HTML extraction is too short")
        return text, 0

    def _extract_pdf(self, url: str) -> tuple[str, int]:
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=120.0,
            headers={"User-Agent": "daily-paper-report/1.0"},
        ) as response:
            response.raise_for_status()
            length = response.headers.get("Content-Length")
            if length and int(length) > _MAX_DOWNLOAD_BYTES:
                raise ValueError("PDF exceeds download limit")
            with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
                total = 0
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_BYTES:
                        raise ValueError("PDF exceeds download limit")
                    handle.write(chunk)
                handle.flush()
                reader = PdfReader(handle.name, strict=False)
                if reader.is_encrypted and reader.decrypt("") == 0:
                    raise FileNotDecryptedError("PDF requires a password")
                if len(reader.pages) > _MAX_PAGES:
                    raise ValueError("PDF exceeds page limit")
                texts: list[str] = []
                failed_pages = 0
                for number, page in enumerate(reader.pages, 1):
                    if _page_stream_size(page) > _MAX_PAGE_STREAM_BYTES:
                        failed_pages += 1
                        continue
                    try:
                        text = page.extract_text(
                            extraction_mode="layout",
                            layout_mode_space_vertically=False,
                        )
                    except (PdfReadError, ValueError, TypeError):
                        failed_pages += 1
                        continue
                    if text:
                        texts.append(f"\n--- Page {number} ---\n{text}")
                joined = _normalize_text("\n".join(texts))
                if len(joined) < _MIN_USEFUL_CHARS:
                    raise ValueError("PDF extraction is too short")
                if failed_pages:
                    joined += (
                        f"\n\n[Extraction note: {failed_pages} page(s) unavailable.]"
                    )
                return joined, len(reader.pages)

    def _load_cache(self, cache_key: str, story_id: str) -> FullTextDocument | None:
        metadata_path = self._cache_dir / f"{cache_key}.json"
        text_path = self._cache_dir / f"{cache_key}.txt"
        if not metadata_path.exists() or not text_path.exists():
            return None
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            text = text_path.read_text(encoding="utf-8")
            if data.get("story_id") != story_id or _sha256(text) != data.get("sha256"):
                return None
            return FullTextDocument(
                story_id=story_id,
                text=text,
                status=FullTextStatus(data["status"]),
                source_url=data.get("source_url"),
                source_format=str(data.get("source_format", "unknown")),
                sha256=str(data["sha256"]),
                page_count=int(data.get("page_count", 0)),
                error=data.get("error"),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _save_cache(self, cache_key: str, document: FullTextDocument) -> None:
        text_path = self._cache_dir / f"{cache_key}.txt"
        metadata_path = self._cache_dir / f"{cache_key}.json"
        text_path.write_text(document.text, encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "story_id": document.story_id,
                    "status": document.status.value,
                    "source_url": document.source_url,
                    "source_format": document.source_format,
                    "sha256": document.sha256,
                    "page_count": document.page_count,
                    "error": document.error,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _candidate_urls(story: Story) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if story.arxiv_id:
        identifier = story.arxiv_id
        candidates.extend(
            [
                ("html", f"https://arxiv.org/html/{identifier}"),
                ("pdf", f"https://arxiv.org/pdf/{identifier}.pdf"),
            ]
        )
    for item in story.raw_items:
        try:
            raw = json.loads(item.raw_json)
        except (json.JSONDecodeError, TypeError):
            continue
        pdf_url = raw.get("pdf_url")
        if isinstance(pdf_url, str) and pdf_url.startswith("https://"):
            candidates.append(("pdf", pdf_url))
    return list(dict.fromkeys(candidates))


def _is_paper(story: Story) -> bool:
    return bool(
        story.arxiv_id
        or any(
            link.link_type.value in {"arxiv", "paper", "openreview"}
            for link in story.links
        )
    )


def _extract_abstract(story: Story) -> str:
    for item in story.raw_items:
        try:
            raw: dict[str, Any] = json.loads(item.raw_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for field in ("abstract_snippet", "summary", "readme_summary"):
            value = raw.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return story.title


def _build_document(
    story_id: str,
    text: str,
    *,
    source_url: str | None,
    source_format: str,
    page_count: int,
    forced_status: FullTextStatus | None = None,
    error: str | None = None,
) -> FullTextDocument:
    normalized = _normalize_text(text)
    status = forced_status or FullTextStatus.COMPLETE
    if len(normalized) > MAX_INPUT_CHARS:
        normalized = _compact_document(normalized)
        status = FullTextStatus.COMPACTED
    if "[Extraction note:" in normalized and status == FullTextStatus.COMPLETE:
        status = FullTextStatus.PARTIAL
    return FullTextDocument(
        story_id=story_id,
        text=normalized,
        status=status,
        source_url=source_url,
        source_format=source_format,
        sha256=_sha256(normalized),
        page_count=page_count,
        error=error,
    )


def _compact_document(text: str) -> str:
    """Keep the whole paper shape while reducing low-value tail sections."""
    budget = MAX_INPUT_CHARS - 10_000
    markers = ["\nReferences\n", "\nREFERENCES\n", "\nBibliography\n"]
    split_at = min((text.find(m) for m in markers if text.find(m) >= 0), default=-1)
    core = text if split_at < 0 else text[:split_at]
    tail = "" if split_at < 0 else text[split_at:]
    if len(core) >= budget:
        half = budget // 2
        return (
            core[:half] + "\n\n[Middle compacted to fit 1M context]\n\n" + core[-half:]
        )
    remaining = budget - len(core)
    return core + "\n\n[References/appendix compacted]\n\n" + tail[:remaining]


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _page_stream_size(page: Any) -> int:
    """Estimate declared content-stream bytes without materializing the stream."""
    try:
        contents = page.get("/Contents")
        objects = contents if isinstance(contents, list) else [contents]
        total = 0
        for obj in objects:
            resolved = obj.get_object() if hasattr(obj, "get_object") else obj
            length = resolved.get("/Length", 0) if hasattr(resolved, "get") else 0
            if hasattr(length, "get_object"):
                length = length.get_object()
            if isinstance(length, int):
                total += length
        return total
    except (KeyError, TypeError, ValueError):
        return 0
