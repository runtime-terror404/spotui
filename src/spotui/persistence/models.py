"""SQLAlchemy entities.

These tables are the durable source of truth. They are deliberately separate
from Pydantic API schemas and from application domain types.
"""

from __future__ import annotations

import time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from spotui.domain.jobs import (
    TERMINAL_JOB_STATES,
    JobState,
    active_states_sql,
)
from spotui.domain.library import LibraryMetadataSource, LibraryScanStatus

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _utc_epoch() -> int:
    return int(time.time())


_STATE_VALUES_SQL = ", ".join(f"'{state.value}'" for state in JobState)
_TERMINAL_VALUES_SQL = ", ".join(f"'{state.value}'" for state in TERMINAL_JOB_STATES)
_SCAN_STATUS_VALUES_SQL = ", ".join(f"'{state.value}'" for state in LibraryScanStatus)
_METADATA_SOURCE_VALUES_SQL = ", ".join(
    f"'{source.value}'" for source in LibraryMetadataSource
)


class DownloadJob(Base):
    """One queued or historical download attempt.

    ``track_key`` is the normalized Amazon track identity. A partial unique
    index prevents two active jobs for the same identity while still allowing
    an explicit re-download after a job reaches a terminal state.
    """

    __tablename__ = "download_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    track_url: Mapped[str] = mapped_column(Text, nullable=False)
    track_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    status_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    progress_phase: Mapped[str | None] = mapped_column(String(40), nullable=True)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance snapshots survive deletion of the import session.
    source_import_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_occurrence_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_playlist_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_utc_epoch, onupdate=_utc_epoch
    )
    started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(f"state IN ({_STATE_VALUES_SQL})", name="state"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "progress_percent IS NULL OR "
            "(progress_percent >= 0 AND progress_percent <= 100)",
            name="progress_percent_range",
        ),
        Index(
            "ux_download_jobs_active_track_key",
            "track_key",
            unique=True,
            sqlite_where=text(active_states_sql()),
        ),
        Index("ix_download_jobs_state_created_at", "state", "created_at"),
    )


class JobAttempt(Base):
    """One subprocess attempt for a download job."""

    __tablename__ = "job_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("download_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_TERMINAL_VALUES_SQL})",
            name="outcome",
        ),
        Index(
            "ux_job_attempts_job_attempt",
            "job_id",
            "attempt_number",
            unique=True,
        ),
        Index(
            "ix_job_attempts_job_id_started_at",
            "job_id",
            "started_at",
        ),
    )


class LibraryRoot(Base):
    """A configured read-only music root and its current index state."""

    __tablename__ = "library_roots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    index_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_checked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_scan_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_utc_epoch, onupdate=_utc_epoch
    )

    __table_args__ = (
        Index("ux_library_roots_path", "path", unique=True),
        CheckConstraint("file_count >= 0", name="file_count_nonnegative"),
    )


class LibraryFile(Base):
    """One indexed audio file under a configured library root."""

    __tablename__ = "library_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    root_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("library_roots.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    album: Mapped[str] = mapped_column(Text, nullable=False, default="")
    track_number: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_source: Mapped[str] = mapped_column(String(20), nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_artist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    amazon_track_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_seen_scan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_utc_epoch, onupdate=_utc_epoch
    )

    __table_args__ = (
        Index("ux_library_files_root_path", "root_id", "path", unique=True),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        CheckConstraint("modified_at_ns >= 0", name="modified_nonnegative"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="duration_nonnegative",
        ),
        CheckConstraint(
            f"metadata_source IN ({_METADATA_SOURCE_VALUES_SQL})",
            name="metadata_source",
        ),
        Index("ix_library_files_normalized_title", "normalized_title"),
        Index("ix_library_files_amazon_track_key", "amazon_track_key"),
        Index(
            "ix_library_files_root_last_seen",
            "root_id",
            "last_seen_scan_id",
        ),
    )


class LibraryScanRun(Base):
    """The outcome and progress counters for one root scan."""

    __tablename__ = "library_scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    root_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("library_roots.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_SCAN_STATUS_VALUES_SQL})",
            name="status",
        ),
        CheckConstraint("files_seen >= 0", name="files_seen_nonnegative"),
        CheckConstraint("files_indexed >= 0", name="files_indexed_nonnegative"),
        CheckConstraint("files_removed >= 0", name="files_removed_nonnegative"),
        CheckConstraint("files_failed >= 0", name="files_failed_nonnegative"),
        Index(
            "ux_library_scan_runs_active",
            "status",
            unique=True,
            sqlite_where=text("status = 'running'"),
        ),
        Index("ix_library_scan_runs_root_started", "root_id", "started_at"),
    )
