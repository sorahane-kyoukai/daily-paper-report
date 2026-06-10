"""Unit tests for status models."""

import pytest

from src.features.status.models import (
    CATEGORY_DISPLAY_NAMES,
    REASON_TEXT_MAP,
    REMEDIATION_HINT_MAP,
    ReasonCode,
    SourceCategory,
    StatusRulePath,
    StatusSummary,
)


class TestReasonCode:
    """Tests for ReasonCode enum."""

    def test_success_states_defined(self) -> None:
        """Verify success reason codes are defined."""
        assert ReasonCode.FETCH_PARSE_OK_HAS_NEW == "FETCH_PARSE_OK_HAS_NEW"
        assert ReasonCode.FETCH_PARSE_OK_HAS_UPDATED == "FETCH_PARSE_OK_HAS_UPDATED"
        assert ReasonCode.FETCH_PARSE_OK_NO_DELTA == "FETCH_PARSE_OK_NO_DELTA"

    def test_cannot_confirm_states_defined(self) -> None:
        """Verify cannot confirm reason codes are defined."""
        assert ReasonCode.DATES_MISSING_NO_ORDERING == "DATES_MISSING_NO_ORDERING"
        assert ReasonCode.DYNAMIC_CONTENT_DETECTED == "DYNAMIC_CONTENT_DETECTED"

    def test_fetch_failure_states_defined(self) -> None:
        """Verify fetch failure reason codes are defined."""
        assert ReasonCode.FETCH_TIMEOUT == "FETCH_TIMEOUT"
        assert ReasonCode.FETCH_HTTP_4XX == "FETCH_HTTP_4XX"
        assert ReasonCode.FETCH_HTTP_5XX == "FETCH_HTTP_5XX"
        assert ReasonCode.FETCH_NETWORK_ERROR == "FETCH_NETWORK_ERROR"
        assert ReasonCode.FETCH_SSL_ERROR == "FETCH_SSL_ERROR"
        assert ReasonCode.FETCH_TOO_LARGE == "FETCH_TOO_LARGE"

    def test_parse_failure_states_defined(self) -> None:
        """Verify parse failure reason codes are defined."""
        assert ReasonCode.PARSE_XML_ERROR == "PARSE_XML_ERROR"
        assert ReasonCode.PARSE_HTML_ERROR == "PARSE_HTML_ERROR"
        assert ReasonCode.PARSE_JSON_ERROR == "PARSE_JSON_ERROR"
        assert ReasonCode.PARSE_SCHEMA_ERROR == "PARSE_SCHEMA_ERROR"
        assert ReasonCode.PARSE_NO_ITEMS == "PARSE_NO_ITEMS"

    def test_all_reason_codes_have_text(self) -> None:
        """All reason codes must have human-readable text."""
        for code in ReasonCode:
            assert code in REASON_TEXT_MAP, f"Missing text for {code}"
            assert len(REASON_TEXT_MAP[code]) > 0


class TestSourceCategory:
    """Tests for SourceCategory enum."""

    def test_all_categories_defined(self) -> None:
        """Verify all categories are defined."""
        assert SourceCategory.INTL_LABS.value == "intl_labs"
        assert SourceCategory.CN_ECOSYSTEM.value == "cn_ecosystem"
        assert SourceCategory.PLATFORMS.value == "platforms"
        assert SourceCategory.PAPER_SOURCES.value == "paper_sources"
        assert SourceCategory.OTHER.value == "other"

    def test_category_count(self) -> None:
        """Verify exactly 5 categories exist."""
        assert len(SourceCategory) == 5

    def test_all_categories_have_display_names(self) -> None:
        """All categories must have display names."""
        for cat in SourceCategory:
            assert cat in CATEGORY_DISPLAY_NAMES, f"Missing display name for {cat}"
            assert len(CATEGORY_DISPLAY_NAMES[cat]) > 0


class TestStatusRulePath:
    """Tests for StatusRulePath model."""

    def test_valid_rule_path(self) -> None:
        """Can create valid rule path."""
        path = StatusRulePath(
            source_id="test-source",
            fetch_ok=True,
            parse_ok=True,
            items_emitted=10,
            items_new=3,
            items_updated=2,
            all_dates_missing=False,
            has_stable_ordering=True,
            is_status_only=False,
            rule_expression="fetch_ok=true+parse_ok=true+new=3+updated=2 => HAS_UPDATE",
            computed_status="HAS_UPDATE",
            computed_reason_code="FETCH_PARSE_OK_HAS_NEW",
        )
        assert path.source_id == "test-source"
        assert path.fetch_ok is True
        assert path.items_new == 3

    def test_rule_path_is_immutable(self) -> None:
        """Rule path is frozen."""
        from pydantic import ValidationError

        path = StatusRulePath(
            source_id="test",
            fetch_ok=True,
            parse_ok=True,
            items_emitted=0,
            items_new=0,
            items_updated=0,
            all_dates_missing=False,
            has_stable_ordering=False,
            is_status_only=False,
            rule_expression="test",
            computed_status="NO_UPDATE",
            computed_reason_code="FETCH_PARSE_OK_NO_DELTA",
        )
        with pytest.raises(ValidationError):
            path.source_id = "changed"  # type: ignore


class TestRemediationHints:
    """Tests for remediation hint mappings."""

    def test_failure_codes_have_hints(self) -> None:
        """Failure codes should have remediation hints."""
        failure_codes = [
            ReasonCode.FETCH_TIMEOUT,
            ReasonCode.FETCH_HTTP_4XX,
            ReasonCode.FETCH_HTTP_5XX,
            ReasonCode.FETCH_NETWORK_ERROR,
            ReasonCode.FETCH_SSL_ERROR,
            ReasonCode.PARSE_XML_ERROR,
            ReasonCode.PARSE_HTML_ERROR,
        ]
        for code in failure_codes:
            assert code in REMEDIATION_HINT_MAP, f"Missing hint for {code}"
            assert REMEDIATION_HINT_MAP[code] is not None

    def test_success_codes_no_hints(self) -> None:
        """Success codes should not have remediation hints."""
        success_codes = [
            ReasonCode.FETCH_PARSE_OK_HAS_NEW,
            ReasonCode.FETCH_PARSE_OK_HAS_UPDATED,
            ReasonCode.FETCH_PARSE_OK_NO_DELTA,
        ]
        for code in success_codes:
            hint = REMEDIATION_HINT_MAP.get(code)
            assert hint is None, f"Success code {code} should not have hint"


class TestStatusSummary:
    """Tests for StatusSummary model."""

    def test_create_valid_summary(self) -> None:
        """Can create valid summary with all counts."""
        summary = StatusSummary(
            total=10,
            has_update=4,
            no_update=2,
            fetch_failed=1,
            parse_failed=1,
            cannot_confirm=1,
            status_only=1,
        )
        assert summary.total == 10
        assert summary.has_update == 4
        assert summary.no_update == 2
        assert summary.fetch_failed == 1
        assert summary.parse_failed == 1
        assert summary.cannot_confirm == 1
        assert summary.status_only == 1

    def test_failed_total_property(self) -> None:
        """Failed total computes fetch + parse failures."""
        summary = StatusSummary(
            total=10,
            has_update=4,
            no_update=2,
            fetch_failed=2,
            parse_failed=1,
            cannot_confirm=1,
            status_only=0,
        )
        assert summary.failed_total == 3

    def test_success_rate_property(self) -> None:
        """Success rate computes percentage of has_update + no_update."""
        summary = StatusSummary(
            total=10,
            has_update=4,
            no_update=2,
            fetch_failed=2,
            parse_failed=1,
            cannot_confirm=1,
            status_only=0,
        )
        assert summary.success_rate == 60.0

    def test_success_rate_zero_total(self) -> None:
        """Success rate returns 0 when total is 0."""
        summary = StatusSummary(
            total=0,
            has_update=0,
            no_update=0,
            fetch_failed=0,
            parse_failed=0,
            cannot_confirm=0,
            status_only=0,
        )
        assert summary.success_rate == 0.0

    def test_summary_is_immutable(self) -> None:
        """Summary is frozen and cannot be modified."""
        from pydantic import ValidationError

        summary = StatusSummary(
            total=10,
            has_update=4,
            no_update=2,
            fetch_failed=2,
            parse_failed=1,
            cannot_confirm=1,
            status_only=0,
        )
        with pytest.raises(ValidationError):
            summary.total = 20  # type: ignore

    def test_negative_counts_rejected(self) -> None:
        """Negative counts are rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            StatusSummary(
                total=-1,
                has_update=0,
                no_update=0,
                fetch_failed=0,
                parse_failed=0,
                cannot_confirm=0,
                status_only=0,
            )
