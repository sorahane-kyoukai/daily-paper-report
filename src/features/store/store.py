"""SQLite state store implementation."""

import sqlite3
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from src.features.store.errors import (
    ConnectionError as StoreConnectionError,
    RunNotFoundError,
)
from src.features.store.metrics import StoreMetrics, TransactionContext
from src.features.store.migrations import CURRENT_VERSION, MigrationManager
from src.features.store.models import (
    DateConfidence,
    HttpCacheEntry,
    Item,
    ItemEventType,
    Run,
    UpsertResult,
)
from src.features.store.url import canonicalize_url


logger = structlog.get_logger()


class StateStore:
    """SQLite state store for items, runs, and HTTP cache headers.

    Provides transactional APIs for managing persistent state across runs.
    Uses WAL mode for reliability and supports schema migrations.
    """

    def __init__(
        self,
        db_path: Path | str,
        strip_params: list[str] | None = None,
        run_id: str | None = None,
    ) -> None:
        """Initialize the state store.

        Args:
            db_path: Path to SQLite database file.
            strip_params: URL parameters to strip for canonicalization.
            run_id: Optional run ID for logging context.
        """
        self._db_path = Path(db_path) if isinstance(db_path, str) else db_path
        self._strip_params = strip_params
        self._run_id = run_id or str(uuid.uuid4())
        self._conn: sqlite3.Connection | None = None
        self._metrics = StoreMetrics.get_instance()
        self._log = logger.bind(
            component="store",
            run_id=self._run_id,
            db_path=str(self._db_path),
        )

    @property
    def db_path(self) -> Path:
        """Get the database path."""
        return self._db_path

    @property
    def run_id(self) -> str:
        """Get the current run ID."""
        return self._run_id

    @property
    def is_connected(self) -> bool:
        """Check if connected to database."""
        return self._conn is not None

    def connect(self) -> None:
        """Open connection to database and apply migrations.

        Creates the database file and parent directories if they don't exist.
        Enables WAL mode for reliability.
        """
        if self._conn is not None:
            return

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._log.info("connecting_to_database")

        # Connect with row factory for named access
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for reliability
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # Apply migrations
        migration_mgr = MigrationManager(self._conn)
        old_version = migration_mgr.get_current_version()
        applied = migration_mgr.apply_migrations()

        self._log.info(
            "database_connected",
            old_version=old_version,
            new_version=CURRENT_VERSION,
            migrations_applied=applied,
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._log.info("database_closed")

    def __enter__(self) -> "StateStore":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Context manager exit."""
        self.close()

    def _ensure_connected(self) -> sqlite3.Connection:
        """Ensure database is connected.

        Returns:
            The database connection.

        Raises:
            StoreConnectionError: If not connected.
        """
        if self._conn is None:
            raise StoreConnectionError("Database not connected. Call connect() first.")
        return self._conn

    @contextmanager
    def _transaction(self, operation: str) -> Generator[TransactionContext]:
        """Context manager for transactions with timing and logging.

        Args:
            operation: Name of the operation for logging.

        Yields:
            Transaction context with timing information.
        """
        conn = self._ensure_connected()
        tx_id = str(uuid.uuid4())[:8]
        start_ns = time.perf_counter_ns()
        ctx = TransactionContext(
            tx_id=tx_id, start_time_ns=start_ns, operation=operation
        )

        self._log.debug(
            "transaction_started",
            tx_id=tx_id,
            op=operation,
        )

        try:
            yield ctx
            conn.commit()
            duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self._metrics.record_tx_duration(duration_ms)

            self._log.info(
                "transaction_complete",
                tx_id=tx_id,
                op=operation,
                affected_rows=ctx.affected_rows,
                duration_ms=round(duration_ms, 2),
            )

        except Exception:
            conn.rollback()
            duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

            self._log.error(
                "transaction_failed",
                tx_id=tx_id,
                op=operation,
                duration_ms=round(duration_ms, 2),
            )
            raise

    # ===== Run Lifecycle =====

    def begin_run(self, run_id: str | None = None) -> Run:
        """Begin a new run.

        Args:
            run_id: Optional run ID (generated if not provided).

        Returns:
            The created Run record.
        """
        run_id = run_id or self._run_id
        now = datetime.now(UTC)

        with self._transaction("begin_run") as ctx:
            conn = self._ensure_connected()
            conn.execute(
                """
                INSERT INTO runs (run_id, started_at, finished_at, success, error_summary)
                VALUES (?, ?, NULL, NULL, NULL)
                """,
                (run_id, now.isoformat()),
            )
            ctx.add_affected_rows(1)

        return Run(run_id=run_id, started_at=now)

    def end_run(
        self,
        run_id: str,
        success: bool,
        error_summary: str | None = None,
    ) -> Run:
        """End a run.

        Args:
            run_id: The run ID to end.
            success: Whether the run succeeded.
            error_summary: Optional error summary if failed.

        Returns:
            The updated Run record.
        """
        now = datetime.now(UTC)

        with self._transaction("end_run") as ctx:
            conn = self._ensure_connected()
            cursor = conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, success = ?, error_summary = ?
                WHERE run_id = ?
                """,
                (
                    now.isoformat(),
                    1 if success else 0,
                    error_summary,
                    run_id,
                ),
            )
            ctx.add_affected_rows(cursor.rowcount)

        run = self.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    def get_run(self, run_id: str) -> Run | None:
        """Get a run by ID.

        Args:
            run_id: The run ID to look up.

        Returns:
            The Run record, or None if not found.
        """
        conn = self._ensure_connected()
        cursor = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return Run(
            run_id=row["run_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=(
                datetime.fromisoformat(row["finished_at"])
                if row["finished_at"]
                else None
            ),
            success=bool(row["success"]) if row["success"] is not None else None,
            error_summary=row["error_summary"],
        )

    def get_last_successful_run_finished_at(self) -> datetime | None:
        """Get the finish time of the last successful run.

        Returns:
            The finish timestamp, or None if no successful runs.
        """
        conn = self._ensure_connected()
        cursor = conn.execute(
            """
            SELECT finished_at FROM runs
            WHERE success = 1 AND finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()

        if row is None:
            return None

        finished_at = datetime.fromisoformat(row["finished_at"])

        # Update metrics
        age_seconds = (datetime.now(UTC) - finished_at).total_seconds()
        self._metrics.record_last_success_age(age_seconds)

        return finished_at

    # ===== Item Operations =====

    def _build_result_item(
        self,
        item: Item,
        canonical_url: str,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> Item:
        """Build a result Item with actual stored values.

        Args:
            item: Original item with source data.
            canonical_url: The canonicalized URL.
            first_seen_at: When item was first seen.
            last_seen_at: When item was last seen.

        Returns:
            Item with stored field values.
        """
        return Item(
            url=canonical_url,
            source_id=item.source_id,
            tier=item.tier,
            kind=item.kind,
            title=item.title,
            published_at=item.published_at,
            date_confidence=item.date_confidence,
            content_hash=item.content_hash,
            raw_json=item.raw_json,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )

    def _insert_new_item(
        self,
        conn: sqlite3.Connection,
        item: Item,
        canonical_url: str,
        now: datetime,
    ) -> None:
        """Insert a new item into the database.

        Args:
            conn: Database connection.
            item: Item to insert.
            canonical_url: The canonicalized URL.
            now: Current timestamp.
        """
        conn.execute(
            """
            INSERT INTO items (
                url, source_id, tier, kind, title, published_at,
                date_confidence, content_hash, raw_json,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_url,
                item.source_id,
                item.tier,
                item.kind,
                item.title,
                item.published_at.isoformat() if item.published_at else None,
                item.date_confidence.value,
                item.content_hash,
                item.raw_json,
                now.isoformat(),
                now.isoformat(),
            ),
        )

    def _update_item_content(
        self,
        conn: sqlite3.Connection,
        item: Item,
        canonical_url: str,
        now: datetime,
    ) -> None:
        """Update an item's content (content_hash changed).

        Args:
            conn: Database connection.
            item: Item with new content.
            canonical_url: The canonicalized URL.
            now: Current timestamp.
        """
        conn.execute(
            """
            UPDATE items SET
                source_id = ?, tier = ?, kind = ?, title = ?,
                published_at = ?, date_confidence = ?,
                content_hash = ?, raw_json = ?, last_seen_at = ?
            WHERE url = ?
            """,
            (
                item.source_id,
                item.tier,
                item.kind,
                item.title,
                item.published_at.isoformat() if item.published_at else None,
                item.date_confidence.value,
                item.content_hash,
                item.raw_json,
                now.isoformat(),
                canonical_url,
            ),
        )

    def upsert_item(self, item: Item) -> UpsertResult:
        """Upsert an item with idempotent semantics.

        - If URL doesn't exist: insert as NEW, set first_seen_at
        - If URL exists with same content_hash: update last_seen_at only (UNCHANGED)
        - If URL exists with different content_hash: update all fields (UPDATED)

        Args:
            item: The item to upsert.

        Returns:
            Result indicating what happened.
        """
        canonical_url = canonicalize_url(item.url, self._strip_params)
        now = datetime.now(UTC)

        with self._transaction("upsert_item") as ctx:
            conn = self._ensure_connected()

            # Check if item exists
            cursor = conn.execute(
                "SELECT url, content_hash, first_seen_at FROM items WHERE url = ?",
                (canonical_url,),
            )
            existing = cursor.fetchone()

            if existing is None:
                # New item
                self._insert_new_item(conn, item, canonical_url, now)
                ctx.add_affected_rows(1)
                self._metrics.record_upsert()

                result_item = self._build_result_item(
                    item, canonical_url, first_seen_at=now, last_seen_at=now
                )
                return UpsertResult(
                    event_type=ItemEventType.NEW, affected_rows=1, item=result_item
                )

            existing_hash = existing["content_hash"]
            first_seen = datetime.fromisoformat(existing["first_seen_at"])

            if existing_hash == item.content_hash:
                # Unchanged - only update last_seen_at
                conn.execute(
                    "UPDATE items SET last_seen_at = ? WHERE url = ?",
                    (now.isoformat(), canonical_url),
                )
                ctx.add_affected_rows(1)
                self._metrics.record_unchanged()

                result_item = self._build_result_item(
                    item, canonical_url, first_seen_at=first_seen, last_seen_at=now
                )
                return UpsertResult(
                    event_type=ItemEventType.UNCHANGED,
                    affected_rows=1,
                    item=result_item,
                )

            # Updated - content_hash changed
            self._update_item_content(conn, item, canonical_url, now)
            ctx.add_affected_rows(1)
            self._metrics.record_update()

            result_item = self._build_result_item(
                item, canonical_url, first_seen_at=first_seen, last_seen_at=now
            )
            return UpsertResult(
                event_type=ItemEventType.UPDATED, affected_rows=1, item=result_item
            )

    def get_item(self, url: str) -> Item | None:
        """Get an item by URL.

        Args:
            url: The URL to look up (will be canonicalized).

        Returns:
            The Item, or None if not found.
        """
        canonical_url = canonicalize_url(url, self._strip_params)
        conn = self._ensure_connected()
        cursor = conn.execute(
            "SELECT * FROM items WHERE url = ?",
            (canonical_url,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_item(row)

    def get_items_since(self, since: datetime) -> list[Item]:
        """Get items first seen since a timestamp.

        Args:
            since: Get items first seen after this time.

        Returns:
            List of items, ordered by first_seen_at descending.
        """
        conn = self._ensure_connected()
        cursor = conn.execute(
            """
            SELECT * FROM items
            WHERE first_seen_at > ?
            ORDER BY first_seen_at DESC
            """,
            (since.isoformat(),),
        )

        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_items_published_since(
        self, published_since: datetime, first_seen_since: datetime | None = None
    ) -> list[Item]:
        """Get items published since a timestamp.

        This method filters by published_at (original publication time),
        not first_seen_at. Useful for getting only recently published content.

        Args:
            published_since: Get items published after this time.
            first_seen_since: Optional filter for first_seen_at (for this run).

        Returns:
            List of items, ordered by published_at descending.
        """
        conn = self._ensure_connected()

        if first_seen_since is not None:
            # Filter by both published_at and first_seen_at
            cursor = conn.execute(
                """
                SELECT * FROM items
                WHERE published_at IS NOT NULL
                  AND published_at > ?
                  AND first_seen_at > ?
                ORDER BY published_at DESC
                """,
                (published_since.isoformat(), first_seen_since.isoformat()),
            )
        else:
            # Filter by published_at only
            cursor = conn.execute(
                """
                SELECT * FROM items
                WHERE published_at IS NOT NULL
                  AND published_at > ?
                ORDER BY published_at DESC
                """,
                (published_since.isoformat(),),
            )

        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_items_published_in_range(
        self, published_start: datetime, published_end: datetime
    ) -> list[Item]:
        """Get items published within a specific time range.

        Args:
            published_start: Start of the time range (inclusive).
            published_end: End of the time range (exclusive).

        Returns:
            List of items published in the range, ordered by published_at descending.
        """
        conn = self._ensure_connected()
        cursor = conn.execute(
            """
            SELECT * FROM items
            WHERE published_at IS NOT NULL
              AND published_at >= ?
              AND published_at < ?
            ORDER BY published_at DESC
            """,
            (published_start.isoformat(), published_end.isoformat()),
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_items_by_source(self, source_id: str) -> list[Item]:
        """Get all items for a source.

        Args:
            source_id: The source ID to filter by.

        Returns:
            List of items for the source.
        """
        conn = self._ensure_connected()
        cursor = conn.execute(
            """
            SELECT * FROM items
            WHERE source_id = ?
            ORDER BY last_seen_at DESC
            """,
            (source_id,),
        )

        return [self._row_to_item(row) for row in cursor.fetchall()]

    def _row_to_item(self, row: sqlite3.Row) -> Item:
        """Convert a database row to an Item.

        Args:
            row: Database row.

        Returns:
            Item instance.
        """
        return Item(
            url=row["url"],
            source_id=row["source_id"],
            tier=row["tier"],
            kind=row["kind"],
            title=row["title"],
            published_at=(
                datetime.fromisoformat(row["published_at"])
                if row["published_at"]
                else None
            ),
            date_confidence=DateConfidence(row["date_confidence"]),
            content_hash=row["content_hash"],
            raw_json=row["raw_json"],
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
        )

    # ===== HTTP Cache Operations =====

    def upsert_http_cache_headers(self, entry: HttpCacheEntry) -> None:
        """Upsert HTTP cache headers for a source.

        Args:
            entry: The cache entry to upsert.
        """
        with self._transaction("upsert_http_cache") as ctx:
            conn = self._ensure_connected()
            conn.execute(
                """
                INSERT INTO http_cache (source_id, etag, last_modified, last_status, last_fetch_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    etag = excluded.etag,
                    last_modified = excluded.last_modified,
                    last_status = excluded.last_status,
                    last_fetch_at = excluded.last_fetch_at
                """,
                (
                    entry.source_id,
                    entry.etag,
                    entry.last_modified,
                    entry.last_status,
                    entry.last_fetch_at.isoformat(),
                ),
            )
            ctx.add_affected_rows(1)

    def get_http_cache(self, source_id: str) -> HttpCacheEntry | None:
        """Get HTTP cache entry for a source.

        Args:
            source_id: The source ID to look up.

        Returns:
            The cache entry, or None if not found.
        """
        conn = self._ensure_connected()
        cursor = conn.execute(
            "SELECT * FROM http_cache WHERE source_id = ?",
            (source_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return HttpCacheEntry(
            source_id=row["source_id"],
            etag=row["etag"],
            last_modified=row["last_modified"],
            last_status=row["last_status"],
            last_fetch_at=datetime.fromisoformat(row["last_fetch_at"]),
        )

    # ===== Retention =====

    def prune_old_items(self, days: int = 180) -> int:
        """Prune items older than the specified number of days.

        Args:
            days: Number of days to retain.

        Returns:
            Number of items pruned.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        with self._transaction("prune_items") as ctx:
            conn = self._ensure_connected()
            cursor = conn.execute(
                "DELETE FROM items WHERE first_seen_at < ?",
                (cutoff.isoformat(),),
            )
            pruned = cursor.rowcount
            ctx.add_affected_rows(pruned)

        self._metrics.record_items_pruned(pruned)
        self._log.info("items_pruned", count=pruned, days=days)
        return pruned

    def prune_old_runs(self, days: int = 90) -> int:
        """Prune runs older than the specified number of days.

        Args:
            days: Number of days to retain.

        Returns:
            Number of runs pruned.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        with self._transaction("prune_runs") as ctx:
            conn = self._ensure_connected()
            cursor = conn.execute(
                "DELETE FROM runs WHERE started_at < ?",
                (cutoff.isoformat(),),
            )
            pruned = cursor.rowcount
            ctx.add_affected_rows(pruned)

        self._metrics.record_runs_pruned(pruned)
        self._log.info("runs_pruned", count=pruned, days=days)
        return pruned

    # ===== Stats =====

    def get_stats(self) -> dict[str, int]:
        """Get row counts for all tables.

        Returns:
            Dictionary mapping table name to row count.
        """
        conn = self._ensure_connected()

        stats: dict[str, int] = {}

        allowed_tables = frozenset({"runs", "items", "http_cache"})
        for table in allowed_tables:
            cursor = conn.execute(  # nosemgrep: formatted-sql-query
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            )
            stats[table] = cursor.fetchone()[0]

        return stats

    def get_schema_version(self) -> int:
        """Get current schema version.

        Returns:
            Current schema version number.
        """
        conn = self._ensure_connected()
        migration_mgr = MigrationManager(conn)
        return migration_mgr.get_current_version()


# Re-export compute_content_hash for backward compatibility
from src.features.store.hash import compute_content_hash  # noqa: E402, F401
