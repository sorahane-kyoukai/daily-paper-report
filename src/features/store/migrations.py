"""SQLite schema migrations for the state store."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog


logger = structlog.get_logger()

# Current schema version
CURRENT_VERSION = 1


@dataclass(frozen=True)
class Migration:
    """A database migration.

    Attributes:
        version: Target version after applying this migration.
        description: Human-readable description.
        up_sql: SQL to apply the migration.
        down_sql: SQL to rollback the migration.
    """

    version: int
    description: str
    up_sql: str
    down_sql: str


# All migrations in order
MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Initial schema with runs, items, and http_cache tables",
        up_sql="""
-- Runs table: tracks pipeline run lifecycle
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    success INTEGER,
    error_summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_runs_success ON runs(success);

-- HTTP cache table: stores ETag/Last-Modified for conditional requests
CREATE TABLE IF NOT EXISTS http_cache (
    source_id TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    last_status INTEGER,
    last_fetch_at TEXT NOT NULL
);

-- Items table: stores collected items with canonical URLs
CREATE TABLE IF NOT EXISTS items (
    url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    tier INTEGER NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    date_confidence TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_source_id ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_first_seen_at ON items(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_items_last_seen_at ON items(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);
""",
        down_sql="""
DROP INDEX IF EXISTS idx_items_content_hash;
DROP INDEX IF EXISTS idx_items_last_seen_at;
DROP INDEX IF EXISTS idx_items_first_seen_at;
DROP INDEX IF EXISTS idx_items_source_id;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS http_cache;
DROP INDEX IF EXISTS idx_runs_success;
DROP INDEX IF EXISTS idx_runs_started_at;
DROP TABLE IF EXISTS runs;
""",
    ),
]


def get_migrations_to_apply(current_version: int) -> list[Migration]:
    """Get migrations that need to be applied.

    Args:
        current_version: The current schema version.

    Returns:
        List of migrations to apply in order.
    """
    return [m for m in MIGRATIONS if m.version > current_version]


def get_rollback_migration(target_version: int) -> Migration | None:
    """Get the migration to rollback to reach target version.

    Args:
        target_version: The target schema version.

    Returns:
        The migration to rollback, or None if already at target.
    """
    for migration in reversed(MIGRATIONS):
        if migration.version == target_version + 1:
            return migration
    return None


class MigrationManager:
    """Manages SQLite schema migrations."""

    # SQL for schema version tracking table
    VERSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
);
"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Initialize the migration manager.

        Args:
            connection: SQLite connection to manage.
        """
        self._conn = connection
        self._log = logger.bind(component="store", operation="migration")

    def ensure_version_table(self) -> None:
        """Ensure the schema_version table exists."""
        self._conn.execute(self.VERSION_TABLE_SQL)
        self._conn.commit()

    def get_current_version(self) -> int:
        """Get the current schema version.

        Returns:
            Current version number, or 0 if no migrations applied.
        """
        self.ensure_version_table()
        cursor = self._conn.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def apply_migrations(self) -> list[int]:
        """Apply all pending migrations.

        Returns:
            List of version numbers that were applied.
        """
        current = self.get_current_version()
        pending = get_migrations_to_apply(current)

        if not pending:
            self._log.info(
                "no_migrations_pending",
                current_version=current,
            )
            return []

        applied: list[int] = []

        for migration in pending:
            self._log.info(
                "applying_migration",
                version=migration.version,
                description=migration.description,
            )

            try:
                # Execute migration in a transaction
                self._conn.executescript(migration.up_sql)

                # Record the migration
                self._conn.execute(
                    """
                    INSERT INTO schema_version (version, applied_at, description)
                    VALUES (?, ?, ?)
                    """,
                    (
                        migration.version,
                        datetime.now(UTC).isoformat(),
                        migration.description,
                    ),
                )
                self._conn.commit()
                applied.append(migration.version)

                self._log.info(
                    "migration_applied",
                    version=migration.version,
                )

            except Exception as e:
                self._log.error(
                    "migration_failed",
                    version=migration.version,
                    error=str(e),
                )
                self._conn.rollback()
                raise

        return applied

    def rollback_to(self, target_version: int) -> list[int]:
        """Rollback to a specific version.

        Args:
            target_version: The version to rollback to.

        Returns:
            List of version numbers that were rolled back.

        Raises:
            ValueError: If target version is invalid.
        """
        current = self.get_current_version()

        if target_version >= current:
            return []

        if target_version < 0:
            msg = f"Invalid target version: {target_version}"
            raise ValueError(msg)

        rolled_back: list[int] = []

        while self.get_current_version() > target_version:
            current = self.get_current_version()
            migration = get_rollback_migration(target_version)

            if migration is None:
                break

            # Find the migration we're rolling back
            for m in MIGRATIONS:
                if m.version == current:
                    migration = m
                    break
            else:
                break

            self._log.info(
                "rolling_back_migration",
                version=migration.version,
                description=migration.description,
            )

            try:
                self._conn.executescript(migration.down_sql)

                self._conn.execute(
                    "DELETE FROM schema_version WHERE version = ?",
                    (migration.version,),
                )
                self._conn.commit()
                rolled_back.append(migration.version)

                self._log.info(
                    "migration_rolled_back",
                    version=migration.version,
                )

            except Exception as e:
                self._log.error(
                    "rollback_failed",
                    version=migration.version,
                    error=str(e),
                )
                self._conn.rollback()
                raise

        return rolled_back

    def get_applied_migrations(self) -> list[dict[str, str | int]]:
        """Get list of applied migrations.

        Returns:
            List of dicts with version, applied_at, and description.
        """
        self.ensure_version_table()
        cursor = self._conn.execute(
            """
            SELECT version, applied_at, description
            FROM schema_version
            ORDER BY version
            """
        )
        return [
            {
                "version": row[0],
                "applied_at": row[1],
                "description": row[2],
            }
            for row in cursor.fetchall()
        ]
