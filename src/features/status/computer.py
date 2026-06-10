"""Status computation engine for per-source status classification."""

from datetime import datetime

import structlog

from src.collectors.errors import CollectorErrorClass
from src.collectors.runner import RunnerResult, SourceRunResult
from src.collectors.state_machine import SourceState
from src.features.config.schemas.base import SourceMethod
from src.features.config.schemas.sources import SourceConfig
from src.features.status.error_mapper import (
    map_fetch_error_to_reason_code,
    map_parse_error_to_reason_code,
)
from src.features.status.metrics import StatusMetrics
from src.features.status.models import (
    REASON_TEXT_MAP,
    REMEDIATION_HINT_MAP,
    ReasonCode,
    SourceCategory,
    StatusRulePath,
    StatusSummary,
)
from src.features.store.models import UpsertResult
from src.renderer.models import SourceStatus, SourceStatusCode


logger = structlog.get_logger()


class IllegalStatusTransitionError(Exception):
    """Raised when an illegal status transition is detected.

    A source cannot be marked NO_UPDATE if fetch or parse failed.
    """

    def __init__(
        self,
        source_id: str,
        attempted_status: SourceStatusCode,
        reason: str,
    ) -> None:
        """Initialize the error.

        Args:
            source_id: Identifier of the source.
            attempted_status: The attempted status.
            reason: Reason for the illegal transition.
        """
        self.source_id = source_id
        self.attempted_status = attempted_status
        self.reason = reason
        super().__init__(
            f"Illegal status transition for source '{source_id}': "
            f"Cannot assign {attempted_status.value}. Reason: {reason}"
        )


class StatusComputer:
    """Computes per-source status from collector results.

    Implements deterministic status classification rules:
    - HAS_UPDATE: fetch+parse ok, at least one NEW or UPDATED item
    - NO_UPDATE: fetch+parse ok, zero NEW/UPDATED items
    - FETCH_FAILED: HTTP fetch failed
    - PARSE_FAILED: Parse failed after successful fetch
    - CANNOT_CONFIRM: fetch+parse ok but dates missing for all items
    - STATUS_ONLY: source is status-only method

    Enforces illegal transition guards:
    - Cannot mark NO_UPDATE if fetch or parse failed
    """

    def __init__(
        self,
        run_id: str,
        source_configs: dict[str, SourceConfig],
        source_categories: dict[str, SourceCategory] | None = None,
    ) -> None:
        """Initialize the status computer.

        Args:
            run_id: Unique run identifier.
            source_configs: Map of source_id to source configuration.
            source_categories: Optional map of source_id to category.
        """
        self._run_id = run_id
        self._source_configs = source_configs
        self._source_categories = source_categories or {}
        self._metrics = StatusMetrics.get_instance()
        self._log = logger.bind(run_id=run_id, component="status")

    def compute_all(self, runner_result: RunnerResult) -> list[SourceStatus]:
        """Compute status for all sources in a run.

        Args:
            runner_result: Result from the collector runner.

        Returns:
            List of SourceStatus for all sources.
        """
        statuses: list[SourceStatus] = []

        for source_id, source_result in runner_result.source_results.items():
            config = self._source_configs.get(source_id)
            if not config:
                self._log.warning(
                    "source_config_missing",
                    source_id=source_id,
                )
                continue

            status = self.compute_single(source_result, config)
            statuses.append(status)

        # Sort by category then by source_id for deterministic ordering
        statuses.sort(
            key=lambda s: (self._get_category_order(s.source_id), s.source_id)
        )

        self._log.info(
            "status_computation_complete",
            sources_total=len(statuses),
            has_update=sum(
                1 for s in statuses if s.status == SourceStatusCode.HAS_UPDATE
            ),
            no_update=sum(
                1 for s in statuses if s.status == SourceStatusCode.NO_UPDATE
            ),
            fetch_failed=sum(
                1 for s in statuses if s.status == SourceStatusCode.FETCH_FAILED
            ),
            parse_failed=sum(
                1 for s in statuses if s.status == SourceStatusCode.PARSE_FAILED
            ),
            cannot_confirm=sum(
                1 for s in statuses if s.status == SourceStatusCode.CANNOT_CONFIRM
            ),
        )

        return statuses

    def compute_summary(self, statuses: list[SourceStatus]) -> StatusSummary:
        """Compute summary statistics for a list of source statuses.

        Args:
            statuses: List of computed source statuses.

        Returns:
            StatusSummary with pre-computed counts.
        """
        return StatusSummary(
            total=len(statuses),
            has_update=sum(
                1 for s in statuses if s.status == SourceStatusCode.HAS_UPDATE
            ),
            no_update=sum(
                1 for s in statuses if s.status == SourceStatusCode.NO_UPDATE
            ),
            fetch_failed=sum(
                1 for s in statuses if s.status == SourceStatusCode.FETCH_FAILED
            ),
            parse_failed=sum(
                1 for s in statuses if s.status == SourceStatusCode.PARSE_FAILED
            ),
            cannot_confirm=sum(
                1 for s in statuses if s.status == SourceStatusCode.CANNOT_CONFIRM
            ),
            status_only=sum(
                1 for s in statuses if s.status == SourceStatusCode.STATUS_ONLY
            ),
        )

    def compute_single(
        self,
        source_result: SourceRunResult,
        config: SourceConfig,
    ) -> SourceStatus:
        """Compute status for a single source.

        Args:
            source_result: Result from the collector for this source.
            config: Source configuration.

        Returns:
            SourceStatus for this source.
        """
        source_id = source_result.source_id

        # Determine fetch and parse success
        fetch_ok, parse_ok = self._check_fetch_parse_status(source_result)

        # Check if this is a status-only source
        is_status_only = config.method == SourceMethod.STATUS_ONLY

        # Gather item statistics
        items_emitted = source_result.items_emitted
        items_new = source_result.items_new
        items_updated = source_result.items_updated

        # Check for missing dates
        all_dates_missing = self._check_all_dates_missing(source_result.upsert_results)
        has_stable_ordering = self._check_has_stable_ordering(source_result)

        # Compute status and reason code
        status_code, reason_code = self._classify_status(
            source_id=source_id,
            fetch_ok=fetch_ok,
            parse_ok=parse_ok,
            is_status_only=is_status_only,
            items_emitted=items_emitted,
            items_new=items_new,
            items_updated=items_updated,
            all_dates_missing=all_dates_missing,
            has_stable_ordering=has_stable_ordering,
            error_class=source_result.result.error.error_class
            if source_result.result.error
            else None,
        )

        # Get reason text and remediation hint
        reason_text = REASON_TEXT_MAP.get(reason_code, "")
        remediation_hint = REMEDIATION_HINT_MAP.get(reason_code)

        # Get newest item date
        newest_item_date = self._get_newest_item_date(source_result.upsert_results)

        # Get last fetch status code
        last_fetch_status_code = self._get_last_fetch_status_code(source_result)

        # Build rule path for audit logging
        rule_path = StatusRulePath(
            source_id=source_id,
            fetch_ok=fetch_ok,
            parse_ok=parse_ok,
            items_emitted=items_emitted,
            items_new=items_new,
            items_updated=items_updated,
            all_dates_missing=all_dates_missing,
            has_stable_ordering=has_stable_ordering,
            is_status_only=is_status_only,
            rule_expression=self._build_rule_expression(
                fetch_ok,
                parse_ok,
                is_status_only,
                items_new,
                items_updated,
                all_dates_missing,
            ),
            computed_status=status_code.value,
            computed_reason_code=reason_code.value,
        )

        # Log the audit trail
        self._log.info(
            "status_computed",
            source_id=source_id,
            status=status_code.value,
            reason_code=reason_code.value,
            rule_path=rule_path.rule_expression,
        )

        # Record metrics
        if status_code in {
            SourceStatusCode.FETCH_FAILED,
            SourceStatusCode.PARSE_FAILED,
        }:
            self._metrics.record_source_failed(source_id, reason_code.value)
        elif status_code == SourceStatusCode.CANNOT_CONFIRM:
            self._metrics.record_source_cannot_confirm(source_id)

        # Get category for this source
        category = self._source_categories.get(source_id, SourceCategory.OTHER)

        return SourceStatus(
            source_id=source_id,
            name=config.name,
            tier=config.tier.value,
            method=config.method.value,
            status=status_code,
            reason_code=reason_code.value,
            reason_text=reason_text,
            remediation_hint=remediation_hint,
            newest_item_date=newest_item_date,
            last_fetch_status_code=last_fetch_status_code,
            items_new=items_new,
            items_updated=items_updated,
            category=category.value,
        )

    def _check_fetch_parse_status(
        self, source_result: SourceRunResult
    ) -> tuple[bool, bool]:
        """Check if fetch and parse succeeded.

        Args:
            source_result: Result from the collector.

        Returns:
            Tuple of (fetch_ok, parse_ok).
        """
        result = source_result.result

        # Check for fetch error
        if result.error and result.error.error_class == CollectorErrorClass.FETCH:
            return False, False

        # Check for parse error
        if result.error and result.error.error_class == CollectorErrorClass.PARSE:
            return True, False

        # Check for schema error (counts as parse failure)
        if result.error and result.error.error_class == CollectorErrorClass.SCHEMA:
            return True, False

        # Check state machine for failed state
        if result.state == SourceState.SOURCE_FAILED:
            # Determine if it was fetch or parse based on state history
            # If we have items, parse must have partially succeeded
            if source_result.items_emitted > 0:
                return True, True  # Partial success
            return False, False

        return True, True

    def _check_all_dates_missing(self, upsert_results: list[UpsertResult]) -> bool:
        """Check if all items are missing published dates.

        Args:
            upsert_results: List of upsert results from the store.

        Returns:
            True if all items have missing dates.
        """
        if not upsert_results:
            return False

        for result in upsert_results:
            if result.item and result.item.published_at is not None:
                return False

        return True

    def _check_has_stable_ordering(self, source_result: SourceRunResult) -> bool:
        """Check if source has stable ordering identifiers.

        Stable ordering means items can be ordered without dates
        (e.g., arXiv IDs, sequential identifiers).

        Args:
            source_result: Result from the collector.

        Returns:
            True if stable ordering exists.
        """
        # Methods with inherently stable ordering
        stable_methods = {"arxiv_api", "github_releases", "openreview_venue"}
        return source_result.method in stable_methods

    def _classify_status(  # noqa: PLR0911, PLR0913
        self,
        source_id: str,
        fetch_ok: bool,
        parse_ok: bool,
        is_status_only: bool,
        items_emitted: int,
        items_new: int,
        items_updated: int,
        all_dates_missing: bool,
        has_stable_ordering: bool,
        error_class: CollectorErrorClass | None,
    ) -> tuple[SourceStatusCode, ReasonCode]:
        """Classify status and reason code based on rules.

        Args:
            source_id: Source identifier.
            fetch_ok: Whether fetch succeeded.
            parse_ok: Whether parse succeeded.
            is_status_only: Whether source is status-only.
            items_emitted: Number of items emitted.
            items_new: Number of new items.
            items_updated: Number of updated items.
            all_dates_missing: Whether all dates are missing.
            has_stable_ordering: Whether stable ordering exists.
            error_class: Error class if any.

        Returns:
            Tuple of (status_code, reason_code).
        """
        # Rule 1: Status-only sources
        if is_status_only:
            return SourceStatusCode.STATUS_ONLY, ReasonCode.STATUS_ONLY_SOURCE

        # Rule 2: Fetch failed
        if not fetch_ok:
            reason_code = self._map_fetch_error_to_reason_code(error_class)
            return SourceStatusCode.FETCH_FAILED, reason_code

        # Rule 3: Parse failed (after successful fetch)
        if not parse_ok:
            reason_code = self._map_parse_error_to_reason_code(error_class)
            return SourceStatusCode.PARSE_FAILED, reason_code

        # From here, fetch+parse both succeeded

        # Rule 4: Has new or updated items
        if items_new > 0:
            return SourceStatusCode.HAS_UPDATE, ReasonCode.FETCH_PARSE_OK_HAS_NEW

        if items_updated > 0:
            return SourceStatusCode.HAS_UPDATE, ReasonCode.FETCH_PARSE_OK_HAS_UPDATED

        # Rule 5: CANNOT_CONFIRM if all dates missing and no stable ordering
        if items_emitted > 0 and all_dates_missing and not has_stable_ordering:
            return SourceStatusCode.CANNOT_CONFIRM, ReasonCode.DATES_MISSING_NO_ORDERING

        # Rule 6: NO_UPDATE (fetch+parse succeeded, zero new/updated)
        # Guard: Cannot mark NO_UPDATE if fetch or parse failed
        self._guard_no_update_transition(source_id, fetch_ok, parse_ok)
        return SourceStatusCode.NO_UPDATE, ReasonCode.FETCH_PARSE_OK_NO_DELTA

    def _guard_no_update_transition(
        self,
        source_id: str,
        fetch_ok: bool,
        parse_ok: bool,
    ) -> None:
        """Guard against illegal NO_UPDATE transition.

        A source cannot be marked NO_UPDATE if fetch or parse failed.

        Args:
            source_id: Source identifier.
            fetch_ok: Whether fetch succeeded.
            parse_ok: Whether parse succeeded.

        Raises:
            IllegalStatusTransitionError: If transition is illegal.
        """
        if not fetch_ok:
            raise IllegalStatusTransitionError(
                source_id=source_id,
                attempted_status=SourceStatusCode.NO_UPDATE,
                reason="fetch failed",
            )

        if not parse_ok:
            raise IllegalStatusTransitionError(
                source_id=source_id,
                attempted_status=SourceStatusCode.NO_UPDATE,
                reason="parse failed",
            )

    def _map_fetch_error_to_reason_code(
        self,
        error_class: CollectorErrorClass | None,
        error_message: str | None = None,
    ) -> ReasonCode:
        """Map fetch error to reason code.

        Delegates to error_mapper module for extensibility.

        Args:
            error_class: Error class from collector.
            error_message: Optional error message for specific mapping.

        Returns:
            Appropriate reason code.
        """
        return map_fetch_error_to_reason_code(error_class, error_message)

    def _map_parse_error_to_reason_code(
        self,
        error_class: CollectorErrorClass | None,
        error_message: str | None = None,
    ) -> ReasonCode:
        """Map parse error to reason code.

        Delegates to error_mapper module for extensibility.

        Args:
            error_class: Error class from collector.
            error_message: Optional error message for specific mapping.

        Returns:
            Appropriate reason code.
        """
        return map_parse_error_to_reason_code(error_class, error_message)

    def _get_newest_item_date(
        self,
        upsert_results: list[UpsertResult],
    ) -> datetime | None:
        """Get the newest item date from upsert results.

        Args:
            upsert_results: List of upsert results.

        Returns:
            Newest published_at date or None.
        """
        newest: datetime | None = None

        for result in upsert_results:
            if (
                result.item
                and result.item.published_at
                and (newest is None or result.item.published_at > newest)
            ):
                newest = result.item.published_at

        return newest

    def _get_last_fetch_status_code(
        self,
        source_result: SourceRunResult,  # noqa: ARG002
    ) -> int | None:
        """Get the last HTTP status code from fetch.

        Args:
            source_result: Result from the collector.

        Returns:
            HTTP status code or None.
        """
        # Status code would typically come from the fetch result
        # For now, return None as it's not directly available
        # This would be enhanced when fetch results carry status codes
        return None

    def _build_rule_expression(  # noqa: PLR0913
        self,
        fetch_ok: bool,
        parse_ok: bool,
        is_status_only: bool,
        items_new: int,
        items_updated: int,
        all_dates_missing: bool,
    ) -> str:
        """Build a human-readable rule expression for audit logging.

        Args:
            fetch_ok: Whether fetch succeeded.
            parse_ok: Whether parse succeeded.
            is_status_only: Whether source is status-only.
            items_new: Number of new items.
            items_updated: Number of updated items.
            all_dates_missing: Whether all dates are missing.

        Returns:
            Rule expression string.
        """
        parts = []

        if is_status_only:
            parts.append("status_only=true")
            return " => STATUS_ONLY"

        parts.append(f"fetch_ok={fetch_ok}")
        parts.append(f"parse_ok={parse_ok}")

        if fetch_ok and parse_ok:
            parts.append(f"new={items_new}")
            parts.append(f"updated={items_updated}")

            if items_new > 0 or items_updated > 0:
                return "+".join(parts) + " => HAS_UPDATE"
            if all_dates_missing:
                parts.append("dates_missing=true")
                return "+".join(parts) + " => CANNOT_CONFIRM"
            return "+".join(parts) + " => NO_UPDATE"

        if not fetch_ok:
            return "+".join(parts) + " => FETCH_FAILED"

        return "+".join(parts) + " => PARSE_FAILED"

    def _get_category_order(self, source_id: str) -> int:
        """Get sort order for category grouping.

        Args:
            source_id: Source identifier.

        Returns:
            Sort order integer.
        """
        category = self._source_categories.get(source_id, SourceCategory.OTHER)
        order_map = {
            SourceCategory.INTL_LABS: 0,
            SourceCategory.CN_ECOSYSTEM: 1,
            SourceCategory.PLATFORMS: 2,
            SourceCategory.PAPER_SOURCES: 3,
            SourceCategory.OTHER: 4,
        }
        return order_map.get(category, 4)

    def get_sources_by_category(
        self,
        statuses: list[SourceStatus],
    ) -> dict[SourceCategory, list[SourceStatus]]:
        """Group sources by category for UI rendering.

        Args:
            statuses: List of source statuses.

        Returns:
            Dict mapping category to list of statuses.
        """
        grouped: dict[SourceCategory, list[SourceStatus]] = {
            cat: [] for cat in SourceCategory
        }

        for status in statuses:
            category = self._source_categories.get(
                status.source_id, SourceCategory.OTHER
            )
            grouped[category].append(status)

        # Remove empty categories
        return {cat: sources for cat, sources in grouped.items() if sources}
