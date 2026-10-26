from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

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
    assert head_revision() == "0001_initial"
    assert current_revision(database_url) is None

    upgrade_database(database_url)

    assert current_revision(database_url) == "0001_initial"
    check_database_current(database_url)
    engine = create_engine(database_url)
    try:
        assert "download_jobs" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_downgrade_and_reupgrade(database_url: str) -> None:
    upgrade_database(database_url)

    downgrade_database(database_url)

    assert current_revision(database_url) is None
    engine = create_engine(database_url)
    try:
        assert "download_jobs" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_database(database_url)
    assert current_revision(database_url) == "0001_initial"


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
