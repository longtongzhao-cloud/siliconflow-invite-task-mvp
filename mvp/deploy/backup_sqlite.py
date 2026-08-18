from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path


BACKUP_PREFIX = "mvp-"
BACKUP_SUFFIX = ".db"


def create_backup(database: Path, backup_dir: Path, retention_days: int) -> Path:
    database = database.resolve(strict=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = backup_dir.resolve(strict=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"{BACKUP_PREFIX}{timestamp}{BACKUP_SUFFIX}"
    temporary_path: Path | None = None

    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".mvp-backup-", suffix=".tmp", dir=backup_dir
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)

        with closing(
            sqlite3.connect(
                f"file:{database.as_posix()}?mode=ro", uri=True, timeout=30
            )
        ) as source, closing(sqlite3.connect(temporary_path)) as target:
            source.execute("PRAGMA busy_timeout = 30000")
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("backup integrity_check failed")

        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    for candidate in backup_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"):
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
        if candidate != destination and modified < cutoff:
            candidate.unlink()

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--retention-days", type=int, default=7)
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error("--retention-days must be at least 1")

    destination = create_backup(
        args.database, args.backup_dir, args.retention_days
    )
    print(destination)


if __name__ == "__main__":
    main()
