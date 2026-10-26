"""SQLAlchemy entities.

These tables are the durable source of truth. They are deliberately separate
from Pydantic API schemas and from application domain types.
"""

from __future__ import annotations

import time

from sqlalchemy import (
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
