"""Programmatic Alembic operations used by the CLI and startup checks."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


class SchemaNotCurrentError(RuntimeError):
    """The database has no schema or is not at the migration head."""


def migrations_directory() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    if database_url:
        # Pass through attributes rather than set_main_option so SQLite paths
        # containing percent signs are not treated as ConfigParser interpolation.
        config.attributes["db_url"] = database_url
    return config


def head_revision() -> str:
    script = ScriptDirectory.from_config(alembic_config())
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one Alembic head, found {heads}")
    return heads[0]


def current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        if not inspect(engine).has_table("alembic_version"):
            return None
        with engine.connect() as connection:
            revisions = (
                connection.execute(text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
    finally:
        engine.dispose()
    if not revisions:
        return None
    if len(revisions) > 1:
        raise RuntimeError(f"database has multiple Alembic revisions: {revisions}")
    return str(revisions[0])


def upgrade_database(database_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade_database(database_url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(database_url), revision)


def check_database_current(database_url: str) -> None:
    """Fail with an actionable message when migrations have not been applied."""
    current = current_revision(database_url)
    head = head_revision()
    if current is None:
        raise SchemaNotCurrentError(
            "database is not initialized; run 'spotui db upgrade' before starting SpotUI"
        )
    if current != head:
        raise SchemaNotCurrentError(
            f"database schema revision {current!r} is not current (head {head!r}); "
            "run 'spotui db upgrade'"
        )
