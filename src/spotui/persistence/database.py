"""SQLite engine and session construction."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_SQLITE_BUSY_TIMEOUT_MS = 5000


def database_url_for_path(path: Path) -> str:
    """Build a SQLite URL without string interpolation or CWD assumptions."""
    return str(URL.create("sqlite", database=str(path)))


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()


@dataclass(slots=True)
class Database:
    """A SQLAlchemy engine plus session factory for one SpotUI database."""

    engine: Engine
    session_factory: sessionmaker[Session]

    @classmethod
    def from_url(cls, url: str | URL) -> Database:
        url_string = str(url)
        connect_args = {}
        if url_string.startswith("sqlite"):
            connect_args = {
                "check_same_thread": False,
                "timeout": _SQLITE_BUSY_TIMEOUT_MS / 1000,
            }
        engine = create_engine(url_string, connect_args=connect_args, future=True)
        if url_string.startswith("sqlite"):
            _configure_sqlite(engine)
        return cls(engine=engine, session_factory=sessionmaker(engine, expire_on_commit=False))

    @classmethod
    def from_path(cls, path: Path) -> Database:
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"cannot create database directory {path.parent}: {exc}") from exc
        return cls.from_url(database_url_for_path(path))

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Commit on success, roll back on failure, and always close."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
