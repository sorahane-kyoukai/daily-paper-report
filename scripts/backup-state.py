"""Create a consistent compressed SQLite backup and retain the newest 30."""

from __future__ import annotations

import gzip
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    backup_dir = Path(sys.argv[2]).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    plain = backup_dir / f"state-{timestamp}.sqlite"
    compressed = plain.with_suffix(".sqlite.gz")
    with sqlite3.connect(source) as source_db, sqlite3.connect(plain) as target_db:
        source_db.backup(target_db)
    with (
        plain.open("rb") as input_file,
        gzip.open(compressed, "wb", compresslevel=6) as output,
    ):
        shutil.copyfileobj(input_file, output)
    plain.unlink()
    for stale in sorted(backup_dir.glob("state-*.sqlite.gz"), reverse=True)[30:]:
        stale.unlink()


if __name__ == "__main__":
    main()
