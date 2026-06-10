"""Integration tests for the state store."""

import tempfile
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.features.store.hash import compute_content_hash
from src.features.store.metrics import StoreMetrics
from src.features.store.models import (
    DateConfidence,
    HttpCacheEntry,
    Item,
    ItemEventType,
)
from src.features.store.store import StateStore


@pytest.fixture
def temp_db_path() -> Generator[Path]:
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_state.sqlite"


@pytest.fixture
def store(temp_db_path: Path) -> Generator[StateStore]:
    """Create a connected state store."""
    StoreMetrics.reset()
    store = StateStore(temp_db_path, run_id="test-run-001")
    store.connect()
    yield store
    store.close()


class TestStateStoreConnection:
    """Tests for store connection and setup."""

    def test_connect_creates_database(self, temp_db_path: Path) -> None:
        """Test connecting creates the database file."""
        store = StateStore(temp_db_path)
        assert not temp_db_path.exists()

        store.connect()
        assert temp_db_path.exists()
        store.close()

    def test_connect_creates_parent_dirs(self, temp_db_path: Path) -> None:
        """Test connecting creates parent directories."""
        nested_path = temp_db_path / "subdir" / "state.sqlite"
        store = StateStore(nested_path)
        store.connect()
        assert nested_path.exists()
        store.close()

    def test_context_manager(self, temp_db_path: Path) -> None:
        """Test store works as context manager."""
        with StateStore(temp_db_path) as store:
            assert store.is_connected
            assert store.get_schema_version() > 0

        assert not store.is_connected

    def test_wal_mode_enabled(self, store: StateStore) -> None:
        """Test WAL mode is enabled."""
        conn = store._ensure_connected()
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"


class TestRunLifecycle:
    """Tests for run lifecycle operations."""

    def test_begin_run(self, store: StateStore) -> None:
        """Test beginning a new run."""
        run = store.begin_run("test-run-1")

        assert run.run_id == "test-run-1"
        assert run.started_at is not None
        assert run.finished_at is None
        assert run.success is None

    def test_end_run_success(self, store: StateStore) -> None:
        """Test ending a run successfully."""
        store.begin_run("test-run-1")
        run = store.end_run("test-run-1", success=True)

        assert run.run_id == "test-run-1"
        assert run.finished_at is not None
        assert run.success is True
        assert run.error_summary is None

    def test_end_run_failure(self, store: StateStore) -> None:
        """Test ending a run with failure."""
        store.begin_run("test-run-1")
        run = store.end_run(
            "test-run-1",
            success=False,
            error_summary="Connection timeout",
        )

        assert run.success is False
        assert run.error_summary == "Connection timeout"

    def test_get_run(self, store: StateStore) -> None:
        """Test retrieving a run by ID."""
        store.begin_run("test-run-1")

        run = store.get_run("test-run-1")
        assert run is not None
        assert run.run_id == "test-run-1"

    def test_get_run_not_found(self, store: StateStore) -> None:
        """Test retrieving non-existent run."""
        run = store.get_run("non-existent")
        assert run is None

    def test_get_last_successful_run_finished_at(self, store: StateStore) -> None:
        """Test getting last successful run timestamp."""
        # No runs yet
        assert store.get_last_successful_run_finished_at() is None

        # Failed run
        store.begin_run("run-1")
        store.end_run("run-1", success=False)
        assert store.get_last_successful_run_finished_at() is None

        # Successful run
        store.begin_run("run-2")
        store.end_run("run-2", success=True)
        last_success = store.get_last_successful_run_finished_at()
        assert last_success is not None

        # Another failed run (shouldn't change last_success)
        store.begin_run("run-3")
        store.end_run("run-3", success=False)
        assert store.get_last_successful_run_finished_at() == last_success


class TestItemOperations:
    """Tests for item upsert and query operations."""

    def test_upsert_new_item(self, store: StateStore) -> None:
        """Test upserting a new item."""
        item = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test Article",
            content_hash="abc123",
            raw_json='{"key": "value"}',
        )

        result = store.upsert_item(item)

        assert result.event_type == ItemEventType.NEW
        assert result.affected_rows == 1
        assert result.item.url == "https://example.com/article"
        assert result.item.first_seen_at is not None

    def test_upsert_unchanged_item(self, store: StateStore) -> None:
        """Test upserting unchanged item only updates last_seen_at."""
        item = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test Article",
            content_hash="abc123",
            raw_json="{}",
        )

        # First upsert
        result1 = store.upsert_item(item)
        first_seen = result1.item.first_seen_at

        # Second upsert with same hash
        result2 = store.upsert_item(item)

        assert result2.event_type == ItemEventType.UNCHANGED
        assert result2.item.first_seen_at == first_seen  # Invariant!
        assert result2.item.last_seen_at > result1.item.last_seen_at

    def test_upsert_updated_item(self, store: StateStore) -> None:
        """Test upserting item with changed content_hash."""
        item1 = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test Article",
            content_hash="abc123",
            raw_json='{"version": 1}',
        )

        # First upsert
        result1 = store.upsert_item(item1)
        first_seen = result1.item.first_seen_at

        # Second upsert with different hash
        item2 = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test Article (Updated)",
            content_hash="def456",  # Changed!
            raw_json='{"version": 2}',
        )

        result2 = store.upsert_item(item2)

        assert result2.event_type == ItemEventType.UPDATED
        assert result2.item.first_seen_at == first_seen  # Invariant!
        assert result2.item.title == "Test Article (Updated)"
        assert result2.item.content_hash == "def456"

    def test_url_canonicalization_on_upsert(self, store: StateStore) -> None:
        """Test URLs are canonicalized on upsert."""
        item = Item(
            url="https://example.com/article?utm_source=twitter",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )

        result = store.upsert_item(item)
        # URL should have tracking param stripped
        assert "utm_source" not in result.item.url
        assert result.item.url == "https://example.com/article"

    def test_get_item(self, store: StateStore) -> None:
        """Test retrieving an item by URL."""
        item = Item(
            url="https://example.com/article",
            source_id="test-source",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )
        store.upsert_item(item)

        retrieved = store.get_item("https://example.com/article")
        assert retrieved is not None
        assert retrieved.title == "Test"

    def test_get_item_not_found(self, store: StateStore) -> None:
        """Test retrieving non-existent item."""
        assert store.get_item("https://example.com/nonexistent") is None

    def test_get_items_since(self, store: StateStore) -> None:
        """Test getting items since a timestamp."""
        # Insert items
        for i in range(3):
            item = Item(
                url=f"https://example.com/article-{i}",
                source_id="test-source",
                tier=0,
                kind="blog",
                title=f"Article {i}",
                content_hash=f"hash{i}",
                raw_json="{}",
            )
            store.upsert_item(item)

        # Get items since a past timestamp
        past = datetime.now(UTC) - timedelta(hours=1)
        items = store.get_items_since(past)

        assert len(items) == 3

    def test_get_items_by_source(self, store: StateStore) -> None:
        """Test getting items filtered by source."""
        # Insert items from different sources
        for source_id in ["source-a", "source-b", "source-a"]:
            item = Item(
                url=f"https://example.com/{source_id}/{hash(source_id + str(datetime.now()))}",
                source_id=source_id,
                tier=0,
                kind="blog",
                title="Test",
                content_hash=f"hash{hash(source_id)}",
                raw_json="{}",
            )
            store.upsert_item(item)

        items_a = store.get_items_by_source("source-a")
        items_b = store.get_items_by_source("source-b")

        assert len(items_a) == 2
        assert len(items_b) == 1


class TestHttpCache:
    """Tests for HTTP cache operations."""

    def test_upsert_http_cache(self, store: StateStore) -> None:
        """Test upserting HTTP cache entry."""
        entry = HttpCacheEntry(
            source_id="test-source",
            etag='"abc123"',
            last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
            last_status=200,
        )

        store.upsert_http_cache_headers(entry)

        retrieved = store.get_http_cache("test-source")
        assert retrieved is not None
        assert retrieved.etag == '"abc123"'
        assert retrieved.last_status == 200

    def test_upsert_http_cache_updates(self, store: StateStore) -> None:
        """Test upserting updates existing entry."""
        entry1 = HttpCacheEntry(
            source_id="test-source",
            etag='"v1"',
            last_status=200,
        )
        store.upsert_http_cache_headers(entry1)

        entry2 = HttpCacheEntry(
            source_id="test-source",
            etag='"v2"',
            last_status=304,
        )
        store.upsert_http_cache_headers(entry2)

        retrieved = store.get_http_cache("test-source")
        assert retrieved is not None
        assert retrieved.etag == '"v2"'
        assert retrieved.last_status == 304

    def test_get_http_cache_not_found(self, store: StateStore) -> None:
        """Test retrieving non-existent cache entry."""
        assert store.get_http_cache("nonexistent") is None


class TestRetention:
    """Tests for retention and pruning."""

    def test_prune_old_items(self, store: StateStore) -> None:
        """Test pruning old items."""
        # Insert an item
        item = Item(
            url="https://example.com/old-article",
            source_id="test",
            tier=0,
            kind="blog",
            title="Old",
            content_hash="abc",
            raw_json="{}",
        )
        store.upsert_item(item)

        # Prune with 180 days retention (should not prune new item)
        pruned = store.prune_old_items(days=180)
        assert pruned == 0

        # Manually update first_seen_at to be old (for testing)
        conn = store._ensure_connected()
        old_date = (datetime.now(UTC) - timedelta(days=200)).isoformat()
        conn.execute(
            "UPDATE items SET first_seen_at = ? WHERE url = ?",
            (old_date, "https://example.com/old-article"),
        )
        conn.commit()

        # Now prune should remove the old item (older than 180 days)
        pruned = store.prune_old_items(days=180)
        assert pruned == 1

    def test_prune_old_runs(self, store: StateStore) -> None:
        """Test pruning old runs."""
        # Create a run
        store.begin_run("old-run")
        store.end_run("old-run", success=True)

        # Prune with 90 days retention (should not prune new run)
        pruned = store.prune_old_runs(days=90)
        assert pruned == 0

        # Manually update started_at to be old (for testing)
        conn = store._ensure_connected()
        old_date = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE runs SET started_at = ? WHERE run_id = ?",
            (old_date, "old-run"),
        )
        conn.commit()

        # Now prune should remove the old run (older than 90 days)
        pruned = store.prune_old_runs(days=90)
        assert pruned == 1


class TestStats:
    """Tests for database statistics."""

    def test_get_stats(self, store: StateStore) -> None:
        """Test getting row counts."""
        stats = store.get_stats()

        assert "runs" in stats
        assert "items" in stats
        assert "http_cache" in stats
        assert all(isinstance(v, int) for v in stats.values())

    def test_stats_reflect_data(self, store: StateStore) -> None:
        """Test stats reflect actual data."""
        # Initially empty
        stats = store.get_stats()
        assert stats["items"] == 0

        # Add items
        for i in range(3):
            item = Item(
                url=f"https://example.com/article-{i}",
                source_id="test",
                tier=0,
                kind="blog",
                title=f"Article {i}",
                content_hash=f"hash{i}",
                raw_json="{}",
            )
            store.upsert_item(item)

        stats = store.get_stats()
        assert stats["items"] == 3


class TestMetrics:
    """Tests for metrics collection."""

    def test_metrics_recorded_on_upsert(self, store: StateStore) -> None:
        """Test metrics are recorded during upserts."""
        metrics = StoreMetrics.get_instance()
        initial_upserts = metrics.db_upserts_total

        item = Item(
            url="https://example.com/article",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="abc",
            raw_json="{}",
        )
        store.upsert_item(item)

        assert metrics.db_upserts_total == initial_upserts + 1

    def test_metrics_recorded_on_update(self, store: StateStore) -> None:
        """Test update metrics are recorded."""
        metrics = StoreMetrics.get_instance()

        item1 = Item(
            url="https://example.com/article",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test",
            content_hash="v1",
            raw_json="{}",
        )
        store.upsert_item(item1)

        initial_updates = metrics.db_updates_total

        item2 = Item(
            url="https://example.com/article",
            source_id="test",
            tier=0,
            kind="blog",
            title="Test Updated",
            content_hash="v2",
            raw_json="{}",
        )
        store.upsert_item(item2)

        assert metrics.db_updates_total == initial_updates + 1


class TestContentHash:
    """Tests for content hash computation."""

    def test_compute_content_hash_basic(self) -> None:
        """Test basic content hash computation."""
        hash1 = compute_content_hash(
            title="Test Article",
            url="https://example.com/article",
        )

        assert len(hash1) == 16
        assert hash1.isalnum()

    def test_compute_content_hash_deterministic(self) -> None:
        """Test content hash is deterministic."""
        hash1 = compute_content_hash(
            title="Test Article",
            url="https://example.com/article",
        )
        hash2 = compute_content_hash(
            title="Test Article",
            url="https://example.com/article",
        )

        assert hash1 == hash2

    def test_compute_content_hash_different_for_different_content(self) -> None:
        """Test different content produces different hash."""
        hash1 = compute_content_hash(
            title="Article 1",
            url="https://example.com/article-1",
        )
        hash2 = compute_content_hash(
            title="Article 2",
            url="https://example.com/article-2",
        )

        assert hash1 != hash2

    def test_compute_content_hash_case_insensitive_title(self) -> None:
        """Test title comparison is case-insensitive."""
        hash1 = compute_content_hash(
            title="Test Article",
            url="https://example.com/article",
        )
        hash2 = compute_content_hash(
            title="TEST ARTICLE",
            url="https://example.com/article",
        )

        assert hash1 == hash2


class TestFullRunLifecycleIntegration:
    """Integration tests for complete run lifecycle."""

    def test_complete_run_with_items(self, store: StateStore) -> None:
        """Test a complete run lifecycle with items."""
        # Begin run
        run = store.begin_run("integration-test-run")
        assert run.run_id == "integration-test-run"

        # Upsert items
        items_to_insert = [
            Item(
                url=f"https://example.com/article-{i}",
                source_id="test-source",
                tier=0,
                kind="blog",
                title=f"Article {i}",
                published_at=datetime.now(UTC) if i % 2 == 0 else None,
                date_confidence=DateConfidence.HIGH
                if i % 2 == 0
                else DateConfidence.LOW,
                content_hash=f"hash-{i}",
                raw_json=f'{{"id": {i}}}',
            )
            for i in range(5)
        ]

        results = [store.upsert_item(item) for item in items_to_insert]
        assert all(r.event_type == ItemEventType.NEW for r in results)

        # End run successfully
        run = store.end_run("integration-test-run", success=True)
        assert run.success is True

        # Verify last successful run
        last_success = store.get_last_successful_run_finished_at()
        assert last_success is not None

        # Get items since the run started
        items = store.get_items_since(run.started_at - timedelta(seconds=1))
        assert len(items) == 5

    def test_two_runs_identical_items_idempotent(self, store: StateStore) -> None:
        """Test two runs with identical items are idempotent."""
        items = [
            Item(
                url=f"https://example.com/article-{i}",
                source_id="test",
                tier=0,
                kind="blog",
                title=f"Article {i}",
                content_hash=f"hash-{i}",
                raw_json="{}",
            )
            for i in range(3)
        ]

        # First run
        store.begin_run("run-1")
        results1 = [store.upsert_item(item) for item in items]
        first_seen_times = [r.item.first_seen_at for r in results1]
        store.end_run("run-1", success=True)

        assert all(r.event_type == ItemEventType.NEW for r in results1)

        # Second run with same items
        store.begin_run("run-2")
        results2 = [store.upsert_item(item) for item in items]
        store.end_run("run-2", success=True)

        # All should be UNCHANGED
        assert all(r.event_type == ItemEventType.UNCHANGED for r in results2)

        # first_seen_at should be preserved
        for r, orig_first_seen in zip(results2, first_seen_times, strict=True):
            assert r.item.first_seen_at == orig_first_seen

        # Item count should still be 3
        stats = store.get_stats()
        assert stats["items"] == 3
