from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from spotui.persistence.migrate import (
    SchemaNotCurrentError,
    check_database_current,
    current_revision,
    downgrade_database,
    head_revision,
    upgrade_database,
)
from spotui.persistence.models import Base


def test_database_must_be_migrated_before_use(database_url: str) -> None:
    with pytest.raises(SchemaNotCurrentError, match="spotui db upgrade"):
        check_database_current(database_url)


def test_upgrade_from_empty_database(database_url: str) -> None:
    head = head_revision()
    assert current_revision(database_url) is None

    upgrade_database(database_url)

    assert current_revision(database_url) == head
    check_database_current(database_url)
    engine = create_engine(database_url)
    try:
        tables = inspect(engine).get_table_names()
        assert "download_jobs" in tables
        assert "job_attempts" in tables
        assert "library_roots" in tables
        assert "library_files" in tables
        assert "library_scan_runs" in tables
        assert "import_sessions" in tables
        assert "source_tracks" in tables
        assert "amazon_candidates" in tables
        assert "paired_devices" in tables
        assert "legacy_queue_imports" in tables
    finally:
        engine.dispose()


def test_downgrade_and_reupgrade(database_url: str) -> None:
    upgrade_database(database_url)

    downgrade_database(database_url)

    assert current_revision(database_url) is None
    engine = create_engine(database_url)
    try:
        tables = inspect(engine).get_table_names()
        assert "download_jobs" not in tables
        assert "job_attempts" not in tables
        assert "library_roots" not in tables
        assert "library_files" not in tables
        assert "library_scan_runs" not in tables
        assert "import_sessions" not in tables
        assert "source_tracks" not in tables
        assert "amazon_candidates" not in tables
        assert "paired_devices" not in tables
        assert "legacy_queue_imports" not in tables
    finally:
        engine.dispose()

    upgrade_database(database_url)
    assert current_revision(database_url) == head_revision()


def test_models_match_latest_migration(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == []


def test_alembic_ini_uses_xdg_database(env) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env.paths.ensure_runtime_directories()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )

    assert result.returncode == 0, result.stderr
    assert env.paths.database_file.exists()
    assert current_revision(f"sqlite:///{env.paths.database_file}") == head_revision()


def test_upgrade_from_0001_preserves_existing_jobs(database_url: str) -> None:
    upgrade_database(database_url, "0001_initial")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO download_jobs (
                        id, track_url, track_key, title, artist, state,
                        status_message, attempt_count, created_at, updated_at
                    ) VALUES (
                        'legacyjob', 'https://music.amazon.com/tracks/B002TRACK1',
                        'amazon:B002TRACK1', 'Song', 'Artist', 'queued',
                        'queued', 0, 1, 1
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    upgrade_database(database_url)

    assert current_revision(database_url) == head_revision()
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            title = connection.execute(
                text("SELECT title FROM download_jobs WHERE id = 'legacyjob'")
            ).scalar_one()
        tables = inspect(engine).get_table_names()
        assert title == "Song"
        assert "job_attempts" in tables
        assert "library_roots" in tables
    finally:
        engine.dispose()


def test_upgrade_from_0002_adds_library_index(database_url: str) -> None:
    upgrade_database(database_url, "0002_job_attempts")

    upgrade_database(database_url)

    assert current_revision(database_url) == head_revision()
    engine = create_engine(database_url)
    try:
        tables = inspect(engine).get_table_names()
        assert "library_roots" in tables
        assert "library_files" in tables
        assert "library_scan_runs" in tables
        assert "import_sessions" in tables
    finally:
        engine.dispose()


def test_upgrade_from_0003_adds_import_tables(database_url: str) -> None:
    upgrade_database(database_url, "0003_library_index")

    upgrade_database(database_url)

    assert current_revision(database_url) == head_revision()
    engine = create_engine(database_url)
    try:
        tables = inspect(engine).get_table_names()
        assert "import_sessions" in tables
        assert "source_tracks" in tables
        assert "amazon_candidates" in tables
        assert "paired_devices" in tables
        assert "legacy_queue_imports" in tables
    finally:
        engine.dispose()


def test_upgrade_from_0004_adds_paired_devices(database_url: str) -> None:
    upgrade_database(database_url, "0004_spotify_imports")

    upgrade_database(database_url)

    assert current_revision(database_url) == head_revision()
    engine = create_engine(database_url)
    try:
        tables = inspect(engine).get_table_names()
        assert "paired_devices" in tables
        assert "legacy_queue_imports" in tables
    finally:
        engine.dispose()


def test_upgrade_from_0005_adds_legacy_migration_ledger(database_url: str) -> None:
    upgrade_database(database_url, "0005_paired_devices")

    upgrade_database(database_url)

    assert current_revision(database_url) == head_revision()
    engine = create_engine(database_url)
    try:
        assert "legacy_queue_imports" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
