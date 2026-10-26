"""Verified SQLite backups used before applying schema migrations."""

from __future__ import annotations

import os
import re
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

_BACKUP_RE = re.compile(r"^spotui-\d{8}T\d{6}Z(?:-\d+)?\.sqlite3$")


class BackupError(RuntimeError):
    """A database backup could not be created or verified."""


def backup_database(
    database_file: Path,
    backup_dir: Path,
    *,
    target: Path | None = None,
    keep: int = 5,
    clock: Callable[[], float] = time.time,
) -> Path:
    """Create an online SQLite backup, verify it, and prune old spotui backups.

    The SQLite backup API is safe while the source database is in WAL mode.
    The caller should still stop the server before applying schema migrations.
    An explicit *target* file is verified but not subject to retention.
    """
    if keep < 1:
        raise BackupError("backup retention must be at least one file")
    if not database_file.is_file():
        raise BackupError(f"database does not exist: {database_file}")
    if target is None:
        try:
            backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupError(
                f"cannot create backup directory {backup_dir}: {exc}"
            ) from exc
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(clock()))
        target = backup_dir / f"spotui-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_dir / f"spotui-{stamp}-{suffix}.sqlite3"
            suffix += 1
    else:
        if target.exists():
            raise BackupError(f"backup target already exists: {target}")
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupError(
                f"cannot create backup directory {target.parent}: {exc}"
            ) from exc

    try:
        # Open the source normally so SQLite can read a WAL left by a cleanly
        # stopped server. The backup API itself only reads source pages.
        with sqlite3.connect(database_file) as source:
            with sqlite3.connect(target) as destination:
                source.backup(destination)
        os.chmod(target, 0o600)
    except (OSError, sqlite3.Error) as exc:
        target.unlink(missing_ok=True)
        raise BackupError(f"database backup failed: {exc}") from exc

    if not _backup_is_healthy(target):
        target.unlink(missing_ok=True)
        raise BackupError("database backup failed its integrity check")

    if backup_dir == target.parent:
        _prune_backups(backup_dir, keep=keep)
    return target


def _backup_is_healthy(path: Path) -> bool:
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error:
        return False
    return len(result) == 1 and result[0][0] == "ok"


def _prune_backups(backup_dir: Path, *, keep: int) -> None:
    try:
        candidates = sorted(
            (
                entry
                for entry in backup_dir.iterdir()
                if entry.is_file() and _BACKUP_RE.match(entry.name)
            ),
            key=lambda entry: entry.name,
            reverse=True,
        )
    except OSError:
        return
    for obsolete in candidates[keep:]:
        try:
            obsolete.unlink()
        except OSError:
            continue


__all__ = ["BackupError", "backup_database"]
