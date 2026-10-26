"""Alembic environment for SpotUI.

The database URL is resolved, in order, from an explicit ``db_url`` attribute
used by the SpotUI CLI, ``SPOTUI_DATABASE_URL`` for controlled automation, or
the default XDG data directory. No credentials belong in ``alembic.ini``.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

from spotui.paths import Paths
from spotui.persistence.database import database_url_for_path
from spotui.persistence.models import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    from_attributes = config.attributes.get("db_url")
    if from_attributes:
        return str(from_attributes)
    from_x_arguments = context.get_x_argument(as_dictionary=True).get("db_url")
    if from_x_arguments:
        return str(from_x_arguments)
    from_environment = os.environ.get("SPOTUI_DATABASE_URL")
    if from_environment:
        return from_environment
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return database_url_for_path(Paths.resolve().database_file)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
