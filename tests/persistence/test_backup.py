from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from spotui.persistence.backup import BackupError, backup_database


def test_backup_is_verified_and_preserves_rows(
    env, migrated_database_url: str
) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(migrated_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO download_jobs (
                        id, track_url, track_key, title, artist, state,
                        status_message, attempt_count, created_at, updated_at
                    ) VALUES (
                        'backupjob', 'https://music.amazon.com/tracks/B000000001',
                        'amazon:B000000001', 'Song', 'Artist', 'queued',
                        'queued', 0, 1, 1
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    backup = backup_database(env.paths.database_file, env.paths.backup_dir)

    assert backup.parent == env.paths.backup_dir
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute(
            "SELECT title FROM download_jobs WHERE id = 'backupjob'"
        ).fetchone() == ("Song",)


def test_explicit_target_must_be_new(env, migrated_database_url: str, tmp_path: Path) -> None:
    target = tmp_path / "manual-backup.sqlite3"
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(BackupError, match="already exists"):
        backup_database(
            env.paths.database_file,
            env.paths.backup_dir,
            target=target,
        )
    assert target.read_text(encoding="utf-8") == "existing"


def test_backup_retention_prunes_only_managed_names(
    env, migrated_database_url: str
) -> None:
    unrelated = env.paths.backup_dir / "notes.txt"
    env.paths.backup_dir.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")

    backups = [
        backup_database(
            env.paths.database_file,
            env.paths.backup_dir,
            keep=2,
            clock=lambda stamp=stamp: stamp,
        )
        for stamp in (1_700_000_000.0, 1_700_000_100.0, 1_700_000_200.0)
    ]

    remaining = sorted(env.paths.backup_dir.glob("spotui-*.sqlite3"))
    assert len(remaining) == 2
    assert remaining == [backups[1], backups[2]]
    assert unrelated.exists()


def test_missing_database_is_a_clear_error(env) -> None:
    with pytest.raises(BackupError, match="does not exist"):
        backup_database(env.paths.database_file, env.paths.backup_dir)
