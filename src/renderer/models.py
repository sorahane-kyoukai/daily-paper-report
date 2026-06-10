"""Data models for the static HTML renderer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.linker.models import Story


if TYPE_CHECKING:
    pass


class SourceStatusCode(str, Enum):
    """Status code for a source.

    - NO_UPDATE: Fetch/parse succeeded, no new/updated items
    - HAS_UPDATE: Fetch/parse succeeded, has new/updated items
    - FETCH_FAILED: HTTP fetch failed
    - PARSE_FAILED: Parsing failed after successful fetch
    - STATUS_ONLY: Source is status-only (no items expected)
    - CANNOT_CONFIRM: Success but dates missing/uncertain
    """

    NO_UPDATE = "NO_UPDATE"
    HAS_UPDATE = "HAS_UPDATE"
    FETCH_FAILED = "FETCH_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    STATUS_ONLY = "STATUS_ONLY"
    CANNOT_CONFIRM = "CANNOT_CONFIRM"


class SourceStatus(BaseModel):
    """Status of a single source for rendering.

    Attributes:
        source_id: Unique source identifier.
        name: Human-readable source name.
        tier: Source tier (0, 1, 2).
        method: Collection method (rss_atom, arxiv_api, etc.).
        status: Status code.
        reason_code: Machine-readable reason.
        reason_text: Human-readable reason.
        remediation_hint: Optional hint for fixing issues.
        newest_item_date: Date of newest item if available.
        last_fetch_status_code: HTTP status code from last fetch.
        items_new: Number of new items this run.
        items_updated: Number of updated items this run.
        category: Source category for UI grouping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: Annotated[str, Field(min_length=1)]
    name: str = ""
    tier: Annotated[int, Field(ge=0, le=2)] = 1
    method: str = ""
    status: SourceStatusCode = SourceStatusCode.NO_UPDATE
    reason_code: str = ""
    reason_text: str = ""
    remediation_hint: str | None = None
    newest_item_date: datetime | None = None
    last_fetch_status_code: int | None = None
    items_new: int = 0
    items_updated: int = 0
    category: str | None = None


class RunInfo(BaseModel):
    """Information about a pipeline run.

    Attributes:
        run_id: Unique run identifier.
        started_at: When run started.
        finished_at: When run finished.
        success: Whether run succeeded.
        error_summary: Error summary if failed.
        items_total: Total items processed.
        stories_total: Total stories produced.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: Annotated[str, Field(min_length=1)]
    started_at: datetime
    finished_at: datetime | None = None
    success: bool | None = None
    error_summary: str | None = None
    items_total: int = 0
    stories_total: int = 0


class DailyDigest(BaseModel):
    """Daily digest data for JSON API output.

    This is the schema for api/daily.json.

    Attributes:
        run_id: Unique run identifier.
        run_date: Date of this run (YYYY-MM-DD).
        generated_at: ISO timestamp when generated.
        top5: Top 5 stories.
        model_releases_by_entity: Model releases grouped by entity.
        papers: Papers section.
        radar: Worth monitoring section.
        sources_status: Per-source status.
        run_info: Run information.
        archive_dates: Available archive dates (YYYY-MM-DD, descending order).
        entity_catalog: Mapping of entity IDs to display details (name, type).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: Annotated[str, Field(min_length=1)]
    run_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    generated_at: str
    top5: list[dict[str, object]] = Field(default_factory=list)
    model_releases_by_entity: dict[str, list[dict[str, object]]] = Field(
        default_factory=dict
    )
    papers: list[dict[str, object]] = Field(default_factory=list)
    radar: list[dict[str, object]] = Field(default_factory=list)
    sources_status: list[dict[str, object]] = Field(default_factory=list)
    run_info: dict[str, object] = Field(default_factory=dict)
    archive_dates: list[str] = Field(default_factory=list)
    entity_catalog: dict[str, dict[str, str]] = Field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedFile:
    """Information about a generated file.

    Attributes:
        path: Relative path from output directory.
        absolute_path: Absolute path to file.
        bytes_written: Number of bytes written.
        sha256: SHA-256 checksum of content.
    """

    path: str
    absolute_path: str
    bytes_written: int
    sha256: str


@dataclass
class RenderManifest:
    """Manifest of rendered files.

    Attributes:
        run_id: Run identifier.
        run_date: Date of run (YYYY-MM-DD).
        generated_at: When rendering completed.
        files: List of generated files.
        total_bytes: Total bytes written.
        duration_ms: Rendering duration in milliseconds.
    """

    run_id: str
    run_date: str
    generated_at: str
    files: list[GeneratedFile] = field(default_factory=list)
    total_bytes: int = 0
    duration_ms: float = 0.0

    def add_file(self, file_info: GeneratedFile) -> None:
        """Add a file to the manifest.

        Args:
            file_info: Information about the generated file.
        """
        self.files.append(file_info)
        self.total_bytes += file_info.bytes_written


@dataclass
class RenderContext:
    """Context for rendering templates.

    Attributes:
        run_id: Run identifier.
        run_date: Date of run (YYYY-MM-DD).
        generated_at: When rendering started.
        timezone: Timezone for date display.
        top5: Top 5 stories.
        model_releases_by_entity: Model releases grouped by entity.
        papers: Papers section.
        radar: Radar section.
        sources_status: Per-source status list.
        recent_runs: Recent run info for status page.
        archive_dates: List of archive dates for archive page.
    """

    run_id: str
    run_date: str
    generated_at: str
    timezone: str = "UTC"
    top5: list[Story] = field(default_factory=list)
    model_releases_by_entity: dict[str, list[Story]] = field(default_factory=dict)
    papers: list[Story] = field(default_factory=list)
    radar: list[Story] = field(default_factory=list)
    sources_status: list[SourceStatus] = field(default_factory=list)
    recent_runs: list[RunInfo] = field(default_factory=list)
    archive_dates: list[str] = field(default_factory=list)


@dataclass
class RenderResult:
    """Result of the rendering operation.

    Attributes:
        success: Whether rendering succeeded.
        manifest: Manifest of generated files.
        error_summary: Error summary if failed.
    """

    success: bool
    manifest: RenderManifest
    error_summary: str | None = None


@dataclass
class RenderConfig:
    """Configuration for static rendering.

    Groups rendering parameters to reduce function argument count.

    Attributes:
        output_dir: Output directory for rendered files.
        run_id: Unique run identifier.
        timezone: Timezone for date display.
        retention_days: Number of days to retain day pages.
    """

    output_dir: str
    run_id: str
    timezone: str = "UTC"
    retention_days: int = 90
