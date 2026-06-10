"""Unit tests for schema migrations."""

import sqlite3
from collections.abc import Generator

import pytest

from src.features.store.migrations import (
    CURRENT_VERSION,
    MIGRATIONS,
    MigrationManager,
    get_migrations_to_apply,
)


class TestMigrationConstants:
    """Tests for migration constants."""

    def test_current_version_positive(self) -> None:
        """Test current version is positive."""
        assert CURRENT_VERSION > 0

    def test_migrations_list_not_empty(self) -> None:
        """Test migrations list is not empty."""
        assert len(MIGRATIONS) > 0

    def test_migrations_in_order(self) -> None:
        """Test migrations are in ascending version order."""
        versions = [m.version for m in MIGRATIONS]
        assert versions == sorted(versions)

    def test_migrations_have_up_and_down(self) -> None:
        """Test all migrations have up and down SQL."""
        for migration in MIGRATIONS:
            assert migration.up_sql.strip()
            assert migration.down_sql.strip()

    def test_current_version_matches_latest_migration(self) -> None:
        """Test current version matches the latest migration."""
        assert MIGRATIONS[-1].version == CURRENT_VERSION


class TestGetMigrationsToApply:
    """Tests for get_migrations_to_apply function."""

    def test_from_zero(self) -> None:
        """Test getting all migrations from version 0."""
        pending = get_migrations_to_apply(0)
        assert len(pending) == len(MIGRATIONS)

    def test_from_current(self) -> None:
        """Test no migrations when at current version."""
        pending = get_migrations_to_apply(CURRENT_VERSION)
        assert len(pending) == 0

    def test_from_intermediate(self) -> None:
        """Test migrations from intermediate version."""
        if len(MIGRATIONS) > 1:
            pending = get_migrations_to_apply(1)
            assert len(pending) == len(MIGRATIONS) - 1


class TestMigrationManager:
    """Tests for MigrationManager."""

    @pytest.fixture
    def temp_db(self) -> Generator[sqlite3.Connection]:
        """Create a temporary in-memory database."""
        conn = sqlite3.connect(":memory:")
        yield conn
        conn.close()

    def test_ensure_version_table_creates_table(
        self, temp_db: sqlite3.Connection
    ) -> None:
        """Test version table is created."""
        manager = MigrationManager(temp_db)
        manager.ensure_version_table()

        # Verify table exists
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        assert cursor.fetchone() is not None

    def test_get_current_version_zero_when_empty(
        self, temp_db: sqlite3.Connection
    ) -> None:
        """Test version is 0 when no migrations applied."""
        manager = MigrationManager(temp_db)
        assert manager.get_current_version() == 0

    def test_apply_migrations(self, temp_db: sqlite3.Connection) -> None:
        """Test applying all migrations."""
        manager = MigrationManager(temp_db)
        applied = manager.apply_migrations()

        assert len(applied) == len(MIGRATIONS)
        assert manager.get_current_version() == CURRENT_VERSION

    def test_apply_migrations_idempotent(self, temp_db: sqlite3.Connection) -> None:
        """Test applying migrations twice is idempotent."""
        manager = MigrationManager(temp_db)

        # First application
        applied1 = manager.apply_migrations()
        assert len(applied1) == len(MIGRATIONS)

        # Second application (should do nothing)
        applied2 = manager.apply_migrations()
        assert len(applied2) == 0
        assert manager.get_current_version() == CURRENT_VERSION

    def test_applied_migrations_recorded(self, temp_db: sqlite3.Connection) -> None:
        """Test applied migrations are recorded in schema_version."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        applied = manager.get_applied_migrations()
        assert len(applied) == len(MIGRATIONS)

        for i, record in enumerate(applied):
            assert record["version"] == MIGRATIONS[i].version
            assert record["description"] == MIGRATIONS[i].description
            assert record["applied_at"] is not None

    def test_tables_created_after_migration(self, temp_db: sqlite3.Connection) -> None:
        """Test required tables exist after migration."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        # Check runs table
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
        )
        assert cursor.fetchone() is not None

        # Check items table
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        )
        assert cursor.fetchone() is not None

        # Check http_cache table
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='http_cache'"
        )
        assert cursor.fetchone() is not None

    def test_rollback_to_zero(self, temp_db: sqlite3.Connection) -> None:
        """Test rolling back all migrations."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        rolled_back = manager.rollback_to(0)
        assert len(rolled_back) == len(MIGRATIONS)
        assert manager.get_current_version() == 0

        # Verify tables are dropped
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        )
        assert cursor.fetchone() is None

    def test_rollback_partial(self, temp_db: sqlite3.Connection) -> None:
        """Test partial rollback (if multiple migrations exist)."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        if len(MIGRATIONS) > 1:
            target = MIGRATIONS[0].version
            rolled_back = manager.rollback_to(target)
            assert len(rolled_back) == len(MIGRATIONS) - 1
            assert manager.get_current_version() == target

    def test_rollback_invalid_version_raises(self, temp_db: sqlite3.Connection) -> None:
        """Test rollback to invalid version raises error."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        with pytest.raises(ValueError, match="Invalid target version"):
            manager.rollback_to(-1)


class TestMigrationSQL:
    """Tests for migration SQL correctness."""

    @pytest.fixture
    def temp_db(self) -> Generator[sqlite3.Connection]:
        """Create a temporary in-memory database."""
        conn = sqlite3.connect(":memory:")
        yield conn
        conn.close()

    def test_items_table_schema(self, temp_db: sqlite3.Connection) -> None:
        """Test items table has correct schema."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        # Get column info
        cursor = temp_db.execute("PRAGMA table_info(items)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "url" in columns
        assert "source_id" in columns
        assert "tier" in columns
        assert "kind" in columns
        assert "title" in columns
        assert "published_at" in columns
        assert "date_confidence" in columns
        assert "content_hash" in columns
        assert "raw_json" in columns
        assert "first_seen_at" in columns
        assert "last_seen_at" in columns

    def test_runs_table_schema(self, temp_db: sqlite3.Connection) -> None:
        """Test runs table has correct schema."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        cursor = temp_db.execute("PRAGMA table_info(runs)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "run_id" in columns
        assert "started_at" in columns
        assert "finished_at" in columns
        assert "success" in columns
        assert "error_summary" in columns

    def test_http_cache_table_schema(self, temp_db: sqlite3.Connection) -> None:
        """Test http_cache table has correct schema."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()

        cursor = temp_db.execute("PRAGMA table_info(http_cache)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "source_id" in columns
        assert "etag" in columns
        assert "last_modified" in columns
        assert "last_status" in columns
        assert "last_fetch_at" in columns
