"""Unit tests for store models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.features.store.models import (
    DateConfidence,
    HttpCacheEntry,
    Item,
    ItemEventType,
    Run,
    UpsertResult,
)


class TestDateConfidence:
    """Tests for DateConfidence enum."""

    def test_values(self) -> None:
        """Test enum values."""
        assert DateConfidence.HIGH.value == "high"
        assert DateConfidence.MEDIUM.value == "medium"
        assert DateConfidence.LOW.value == "low"

    def test_from_string(self) -> None:
        """Test creating from string."""
        assert DateConfidence("high") == DateConfidence.HIGH
        assert DateConfidence("medium") == DateConfidence.MEDIUM
        assert DateConfidence("low") == DateConfidence.LOW


class TestItemEventType:
    """Tests for ItemEventType enum."""

    def test_values(self) -> None:
        """Test enum values."""
        assert ItemEventType.NEW.value == "NEW"
        assert ItemEventType.UPDATED.value == "UPDATED"
        assert ItemEventType.UNCHANGED.value == "UNCHANGED"


class TestItem:
    """Tests for Item model."""

    def test_create_minimal(self) -> None:
        """Test creating item with minimal required fields."""
        item = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test Article",
            content_hash="abc123",
            raw_json="{}",
        )

        assert item.url == "https://example.com/article"
        assert item.source_id == "test-source"
        assert item.tier == 0
        assert item.kind == "blog"
        assert item.title == "Test Article"
        assert item.published_at is None
        assert item.date_confidence == DateConfidence.LOW
        assert item.content_hash == "abc123"
        assert item.raw_json == "{}"
        assert item.first_seen_at is not None
        assert item.last_seen_at is not None

    def test_create_with_all_fields(self) -> None:
        """Test creating item with all fields."""
        now = datetime.now(UTC)
        item = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=1,
            kind="paper",
            title="Test Paper",
            published_at=now,
            date_confidence=DateConfidence.HIGH,
            content_hash="def456",
            raw_json='{"key": "value"}',
            first_seen_at=now,
            last_seen_at=now,
        )

        assert item.published_at == now
        assert item.date_confidence == DateConfidence.HIGH

    def test_date_confidence_coercion(self) -> None:
        """Test that date_confidence can be set from string."""
        item = Item(
            url="https://example.com",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
            date_confidence="high",
        )

        assert item.date_confidence == DateConfidence.HIGH

    def test_tier_validation(self) -> None:
        """Test tier must be 0, 1, or 2."""
        with pytest.raises(ValidationError):
            Item(
                url="https://example.com",
                source_id="test",
                tier=3,  # Invalid
                kind="blog",
                title="Test",
                content_hash="abc",
                raw_json="{}",
            )

    def test_empty_url_rejected(self) -> None:
        """Test empty URL is rejected."""
        with pytest.raises(ValidationError):
            Item(
                url="",
                source_id="test",
                tier=0,
                kind="blog",
                title="Test",
                content_hash="abc",
                raw_json="{}",
            )

    def test_immutable(self) -> None:
        """Test item is immutable (frozen)."""
        item = Item(
            url="https://example.com",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )

        with pytest.raises(ValidationError):
            item.url = "https://other.com"  # type: ignore[misc]


class TestRun:
    """Tests for Run model."""

    def test_create_new_run(self) -> None:
        """Test creating a new run."""
        run = Run(run_id="test-run-123")

        assert run.run_id == "test-run-123"
        assert run.started_at is not None
        assert run.finished_at is None
        assert run.success is None
        assert run.error_summary is None

    def test_create_finished_run(self) -> None:
        """Test creating a finished run."""
        now = datetime.now(UTC)
        run = Run(
            run_id="test-run",
            started_at=now,
            finished_at=now,
            success=True,
        )

        assert run.success is True
        assert run.finished_at == now

    def test_create_failed_run(self) -> None:
        """Test creating a failed run with error summary."""
        run = Run(
            run_id="test-run",
            success=False,
            error_summary="Connection timeout",
        )

        assert run.success is False
        assert run.error_summary == "Connection timeout"


class TestHttpCacheEntry:
    """Tests for HttpCacheEntry model."""

    def test_create_minimal(self) -> None:
        """Test creating entry with minimal fields."""
        entry = HttpCacheEntry(source_id="test-source")

        assert entry.source_id == "test-source"
        assert entry.etag is None
        assert entry.last_modified is None
        assert entry.last_status is None
        assert entry.last_fetch_at is not None

    def test_create_with_headers(self) -> None:
        """Test creating entry with cache headers."""
        entry = HttpCacheEntry(
            source_id="test-source",
            etag='"abc123"',
            last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
            last_status=200,
        )

        assert entry.etag == '"abc123"'
        assert entry.last_modified == "Mon, 01 Jan 2024 00:00:00 GMT"
        assert entry.last_status == 200


class TestUpsertResult:
    """Tests for UpsertResult model."""

    def test_create_new_result(self) -> None:
        """Test creating result for new item."""
        item = Item(
            url="https://example.com",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )

        result = UpsertResult(
            event_type=ItemEventType.NEW,
            affected_rows=1,
            item=item,
        )

        assert result.event_type == ItemEventType.NEW
        assert result.affected_rows == 1
        assert result.item == item

    def test_create_update_result(self) -> None:
        """Test creating result for updated item."""
        item = Item(
            url="https://example.com",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )

        result = UpsertResult(
            event_type=ItemEventType.UPDATED,
            affected_rows=1,
            item=item,
        )

        assert result.event_type == ItemEventType.UPDATED
