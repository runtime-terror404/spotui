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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from spotui.domain.imports import (
    ImportQueueOutcome,
    ImportStatus,
    MatchingStatus,
    ReviewStatus,
)
from spotui.domain.jobs import (
    TERMINAL_JOB_STATES,
    JobState,
    active_states_sql,
)
from spotui.domain.legacy import LegacyImportOutcome
from spotui.domain.library import LibraryMatch, LibraryMetadataSource, LibraryScanStatus
from spotui.domain.spotify import SpotifyEntityType

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
_IMPORT_STATUS_VALUES_SQL = ", ".join(f"'{status.value}'" for status in ImportStatus)
_MATCHING_STATUS_VALUES_SQL = ", ".join(f"'{status.value}'" for status in MatchingStatus)
_REVIEW_STATUS_VALUES_SQL = ", ".join(f"'{status.value}'" for status in ReviewStatus)
_QUEUE_OUTCOME_VALUES_SQL = ", ".join(
    f"'{outcome.value}'" for outcome in ImportQueueOutcome
)
_SPOTIFY_KIND_VALUES_SQL = ", ".join(f"'{kind.value}'" for kind in SpotifyEntityType)
_LIBRARY_MATCH_VALUES_SQL = ", ".join(f"'{match.value}'" for match in LibraryMatch)
_LEGACY_OUTCOME_VALUES_SQL = ", ".join(
    f"'{outcome.value}'" for outcome in LegacyImportOutcome
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


class ImportSession(Base):
    """One persisted Spotify album/playlist import and review session."""

    __tablename__ = "import_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    spotify_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    spotify_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artwork_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_utc_epoch, onupdate=_utc_epoch
    )
    matching_started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matching_completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sources: Mapped[list[SourceTrack]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceTrack.position",
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_IMPORT_STATUS_VALUES_SQL})",
            name="status",
        ),
        CheckConstraint(
            f"spotify_type IS NULL OR spotify_type IN ({_SPOTIFY_KIND_VALUES_SQL})",
            name="spotify_type",
        ),
        CheckConstraint(
            "(status = 'matching_complete' AND active_slot IS NULL) OR "
            "(status IN ('extracting', 'matching', 'paused') AND active_slot = 1)",
            name="active_slot_matches_status",
        ),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        Index(
            "ux_import_sessions_active",
            "active_slot",
            unique=True,
            sqlite_where=text("active_slot IS NOT NULL"),
        ),
        Index("ix_import_sessions_status_created", "status", "created_at"),
    )


class SourceTrack(Base):
    """A source occurrence; duplicates are preserved by position."""

    __tablename__ = "source_tracks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("import_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    spotify_track_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    artist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    matching_status: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    library_match: Mapped[str | None] = mapped_column(String(8), nullable=True)
    queue_outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    queued_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_duplicate_of_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    queued_duplicate_of_source_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_utc_epoch, onupdate=_utc_epoch
    )

    session: Mapped[ImportSession] = relationship(back_populates="sources")
    candidates: Mapped[list[AmazonCandidate]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AmazonCandidate.rank",
    )

    __table_args__ = (
        Index("ux_source_tracks_session_position", "session_id", "position", unique=True),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            f"matching_status IN ({_MATCHING_STATUS_VALUES_SQL})",
            name="matching_status",
        ),
        CheckConstraint(
            f"review_status IN ({_REVIEW_STATUS_VALUES_SQL})",
            name="review_status",
        ),
        CheckConstraint(
            f"queue_outcome IN ({_QUEUE_OUTCOME_VALUES_SQL})",
            name="queue_outcome",
        ),
        CheckConstraint(
            f"library_match IS NULL OR library_match IN ({_LIBRARY_MATCH_VALUES_SQL})",
            name="library_match",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="duration_nonnegative",
        ),
        Index("ix_source_tracks_session_matching", "session_id", "matching_status"),
    )


class PairedDevice(Base):
    """A browser device authenticated by a hashed persistent credential."""

    __tablename__ = "paired_devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)
    last_seen_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ux_paired_devices_credential_hash", "credential_hash", unique=True),
        Index("ix_paired_devices_revoked_at", "revoked_at"),
    )


class AmazonCandidate(Base):
    """A ranked Amazon result for one source occurrence."""

    __tablename__ = "amazon_candidates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_track_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("source_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    track_url: Mapped[str] = mapped_column(Text, nullable=False)
    track_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    artist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    album: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    artwork_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_position: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)

    source: Mapped[SourceTrack] = relationship(back_populates="candidates")

    __table_args__ = (
        Index(
            "ux_amazon_candidates_source_track_key",
            "source_track_id",
            "track_key",
            unique=True,
        ),
        CheckConstraint("provider_position >= 0", name="provider_position_nonnegative"),
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint("score >= 0 AND score <= 1", name="score_range"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="duration_nonnegative",
        ),
        Index("ix_amazon_candidates_source_rank", "source_track_id", "rank"),
    )


class LegacyQueueImport(Base):
    """One processed record from a legacy JSON queue.

    The unique source/key pair is the idempotency ledger. It records skips and
    ambiguous entries too, so a repeated migration reports the same outcome
    instead of retrying or duplicating jobs.
    """

    __tablename__ = "legacy_queue_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    legacy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("download_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    imported_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_utc_epoch)

    __table_args__ = (
        Index(
            "ux_legacy_queue_imports_source_key",
            "source_path",
            "legacy_key",
            unique=True,
        ),
        CheckConstraint(
            f"outcome IN ({_LEGACY_OUTCOME_VALUES_SQL})",
            name="outcome",
        ),
        Index("ix_legacy_queue_imports_source_path", "source_path"),
        Index("ix_legacy_queue_imports_job_id", "job_id"),
    )
