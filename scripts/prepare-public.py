"""Finalize Vue history-mode routes without mutating source-controlled files."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise SystemExit("frontend index.html is missing")
    shutil.copy2(index, root / "404.html")
    for route in ("archive", "sources", "status", "reports"):
        directory = root / route
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(index, directory / "index.html")
    for source_dir, target_dir in (
        (root / "api" / "day", root / "day"),
        (root / "api" / "reports" / "weekly", root / "reports" / "weekly"),
        (root / "api" / "reports" / "monthly", root / "reports" / "monthly"),
    ):
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_dir.is_dir():
            for source in source_dir.glob("*.json"):
                shutil.copy2(index, target_dir / f"{source.stem}.html")
    daily = root / "api" / "daily.json"
    payload = json.loads(daily.read_text(encoding="utf-8"))
    day_dir = root / "api" / "day"
    payload["archive_dates"] = sorted(
        (path.stem for path in day_dir.glob("*.json")), reverse=True
    )
    daily.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    reports_index = root / "api" / "reports" / "index.json"
    if not reports_index.exists():
        reports_index.parent.mkdir(parents=True, exist_ok=True)
        reports_index.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "latest": {"weekly": None, "monthly": None},
                    "weekly": [],
                    "monthly": [],
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
