from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from spotui.persistence.database import Database, database_url_for_path
from spotui.persistence.models import Base, DownloadJob


def _job(job_id: str = "job-1") -> DownloadJob:
    return DownloadJob(
        id=job_id,
        track_url="https://music.amazon.com/tracks/B000000001",
        track_key="B000000001",
        title="A Song",
        artist="An Artist",
        state="queued",
        status_message="queued",
        attempt_count=0,
        created_at=1_700_000_000,
        updated_at=1_700_000_000,
    )


def test_sqlite_pragmas_are_applied(env) -> None:
    database = Database.from_path(env.paths.database_file)
    try:
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    finally:
        database.dispose()


def test_session_scope_commits(env) -> None:
    database = Database.from_path(env.paths.database_file)
    Base.metadata.create_all(database.engine)
    try:
        with database.session_scope() as session:
            session.add(_job())
        with database.session_scope() as session:
            assert session.get(DownloadJob, "job-1") is not None
    finally:
        database.dispose()


def test_session_scope_rolls_back(env) -> None:
    database = Database.from_path(env.paths.database_file)
    Base.metadata.create_all(database.engine)
    try:
        with pytest.raises(IntegrityError):
            with database.session_scope() as session:
                session.add(_job("job-1"))
                session.add(_job("job-1"))  # duplicate primary key
        with database.session_scope() as session:
            assert session.query(DownloadJob).count() == 0
    finally:
        database.dispose()


def test_path_with_spaces_is_supported(env) -> None:
    path = env.data_home / "spotui data" / "library index.sqlite3"
    database = Database.from_path(path)
    try:
        Base.metadata.create_all(database.engine)
        assert path.exists()
    finally:
        database.dispose()


def test_url_for_path_is_absolute(env) -> None:
    path = env.paths.database_file

    url = database_url_for_path(path)

    assert url.startswith("sqlite:///")
    assert str(path) in url
