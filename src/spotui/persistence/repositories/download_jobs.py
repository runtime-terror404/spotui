"""Transactional access to download jobs and their attempts."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from spotui.domain.amazon import AmazonTrackUrl
from spotui.domain.errors import (
    DuplicateActiveJobError,
    JobNotFoundError,
    JobTransitionError,
)
from spotui.domain.jobs import (
    ACTIVE_JOB_STATES,
    TERMINAL_JOB_STATES,
    ClaimedJob,
    DownloadJob,
    EnqueueResult,
    JobState,
    QueueCounts,
)
from spotui.persistence.models import DownloadJob as DownloadJobRow
from spotui.persistence.models import JobAttempt as JobAttemptRow

_ACTIVE_VALUES = tuple(state.value for state in ACTIVE_JOB_STATES)
_RETRYABLE_VALUES = (JobState.FAILED.value, JobState.INTERRUPTED.value)
_DISMISSABLE_VALUES = (
    JobState.QUEUED.value,
    JobState.FAILED.value,
    JobState.INTERRUPTED.value,
    JobState.CANCELLED.value,
)


def _epoch() -> int:
    return int(time.time())


def _to_domain(row: DownloadJobRow) -> DownloadJob:
    return DownloadJob(
        id=row.id,
        track_url=row.track_url,
        track_key=row.track_key,
        title=row.title,
        artist=row.artist,
        state=JobState(row.state),
        status_message=row.status_message,
        progress_phase=row.progress_phase,
        progress_percent=row.progress_percent,
        attempt_count=row.attempt_count,
        last_error=row.last_error,
        output_path=row.output_path,
        source_import_id=row.source_import_id,
        source_occurrence_id=row.source_occurrence_id,
        source_playlist_title=row.source_playlist_title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


class DownloadJobRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], int] = _epoch,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._session_factory

    def enqueue(
        self,
        track: AmazonTrackUrl,
        *,
        title: str,
        artist: str = "",
        source_import_id: str | None = None,
        source_occurrence_id: str | None = None,
        source_playlist_title: str | None = None,
    ) -> EnqueueResult:
        now = self._clock()
        try:
            with self._session_factory.begin() as session:
                existing = self._active_by_key(session, track.track_key)
                if existing is not None:
                    return EnqueueResult(_to_domain(existing), True)
                row = DownloadJobRow(
                    id=uuid.uuid4().hex,
                    track_url=track.original,
                    track_key=track.track_key,
                    title=(title.strip() or track.original),
                    artist=artist.strip(),
                    state=JobState.QUEUED.value,
                    status_message="queued",
                    progress_phase=None,
                    progress_percent=None,
                    attempt_count=0,
                    last_error=None,
                    output_path=None,
                    source_import_id=source_import_id,
                    source_occurrence_id=source_occurrence_id,
                    source_playlist_title=source_playlist_title,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                return EnqueueResult(_to_domain(row), False)
        except IntegrityError:
            with self._session_factory() as session:
                existing = self._active_by_key(session, track.track_key)
                if existing is not None:
                    return EnqueueResult(_to_domain(existing), True)
            raise DuplicateActiveJobError(
                "An active download already exists for this track."
            ) from None

    def get(self, job_id: str) -> DownloadJob:
        with self._session_factory() as session:
            row = session.get(DownloadJobRow, job_id)
            if row is None:
                raise JobNotFoundError("Download job not found.")
            return _to_domain(row)

    def list_jobs(self, *, limit: int = 500) -> tuple[DownloadJob, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DownloadJobRow)
                .order_by(DownloadJobRow.created_at.desc(), DownloadJobRow.id.desc())
                .limit(limit)
            ).all()
            return tuple(_to_domain(row) for row in rows)

    def counts(self) -> QueueCounts:
        with self._session_factory() as session:
            rows = session.execute(
                select(DownloadJobRow.state, func.count()).group_by(DownloadJobRow.state)
            ).all()
        counts = dict(rows)
        return QueueCounts(
            queued=counts.get(JobState.QUEUED.value, 0),
            active=sum(
                counts.get(state.value, 0)
                for state in (
                    JobState.STARTING,
                    JobState.RUNNING,
                    JobState.CANCELLING,
                )
            ),
            completed=counts.get(JobState.COMPLETED.value, 0),
            failed=counts.get(JobState.FAILED.value, 0),
            cancelled=counts.get(JobState.CANCELLED.value, 0),
            interrupted=counts.get(JobState.INTERRUPTED.value, 0),
        )

    def claim_next(self) -> ClaimedJob | None:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = session.scalars(
                select(DownloadJobRow)
                .where(DownloadJobRow.state == JobState.QUEUED.value)
                .order_by(DownloadJobRow.created_at.asc(), DownloadJobRow.id.asc())
                .limit(1)
            ).first()
            if row is None:
                return None
            row.state = JobState.STARTING.value
            row.status_message = "starting…"
            row.progress_phase = "starting"
            row.progress_percent = None
            row.attempt_count += 1
            row.last_error = None
            row.started_at = now
            row.updated_at = now
            attempt = JobAttemptRow(
                job_id=row.id,
                attempt_number=row.attempt_count,
                started_at=now,
            )
            session.add(attempt)
            session.flush()
            return ClaimedJob(job=_to_domain(row), attempt_id=attempt.id)

    def mark_running(self, job_id: str, *, message: str, phase: str) -> DownloadJob:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = self._require(session, job_id)
            if row.state in (JobState.STARTING.value, JobState.RUNNING.value):
                row.state = JobState.RUNNING.value
                row.status_message = message
                row.progress_phase = phase
                row.progress_percent = None
                row.updated_at = now
            return _to_domain(row)

    def update_progress(
        self,
        job_id: str,
        *,
        phase: str,
        message: str,
        percent: float | None = None,
    ) -> DownloadJob | None:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = session.get(DownloadJobRow, job_id)
            if row is None:
                return None
            if row.state in (
                JobState.STARTING.value,
                JobState.RUNNING.value,
                JobState.CANCELLING.value,
            ):
                row.progress_phase = phase
                row.status_message = message
                row.progress_percent = percent
                row.updated_at = now
            return _to_domain(row)

    def request_cancel(self, job_id: str) -> DownloadJob:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = self._require(session, job_id)
            if row.state == JobState.QUEUED.value:
                row.state = JobState.CANCELLED.value
                row.status_message = "cancelled"
                row.progress_phase = None
                row.completed_at = now
                row.updated_at = now
            elif row.state in (JobState.STARTING.value, JobState.RUNNING.value):
                row.state = JobState.CANCELLING.value
                row.status_message = "cancelling…"
                row.updated_at = now
            elif row.state == JobState.CANCELLING.value:
                pass
            elif row.state in TERMINAL_JOB_STATES:
                raise JobTransitionError("This download has already finished.")
            else:
                raise JobTransitionError("This download cannot be cancelled.")
            return _to_domain(row)

    def retry(self, job_id: str) -> DownloadJob:
        now = self._clock()
        try:
            with self._session_factory.begin() as session:
                row = self._require(session, job_id)
                if row.state not in _RETRYABLE_VALUES:
                    raise JobTransitionError(
                        "Only failed or interrupted downloads can be retried."
                    )
                row.state = JobState.QUEUED.value
                row.status_message = "queued again"
                row.progress_phase = None
                row.progress_percent = None
                row.last_error = None
                row.output_path = None
                row.started_at = None
                row.completed_at = None
                row.updated_at = now
                return _to_domain(row)
        except IntegrityError:
            raise DuplicateActiveJobError(
                "Another active download already reserves this track."
            ) from None

    def dismiss(self, job_id: str) -> None:
        """Delete a waiting or finished job without adding it to history.

        The state-qualified delete ensures a job claimed by the worker between
        the read and delete is not removed while its subprocess is active.
        """
        with self._session_factory.begin() as session:
            state = session.scalar(
                select(DownloadJobRow.state).where(DownloadJobRow.id == job_id)
            )
            if state is None:
                raise JobNotFoundError("Download job not found.")
            if state not in _DISMISSABLE_VALUES:
                raise JobTransitionError(
                    "An active download must be cancelled before it can be removed."
                )
            deleted = session.execute(
                delete(DownloadJobRow).where(
                    DownloadJobRow.id == job_id,
                    DownloadJobRow.state == state,
                )
            ).rowcount
            if not deleted:
                raise JobTransitionError(
                    "The download started before it could be removed."
                )

    def recover_interrupted(self) -> int:
        """Mark jobs left active by a previous process as interrupted."""
        now = self._clock()
        recovered = 0
        with self._session_factory.begin() as session:
            rows = session.scalars(
                select(DownloadJobRow).where(
                    DownloadJobRow.state.in_(
                        (
                            JobState.STARTING.value,
                            JobState.RUNNING.value,
                            JobState.CANCELLING.value,
                        )
                    )
                )
            ).all()
            for row in rows:
                row.state = JobState.INTERRUPTED.value
                row.status_message = "interrupted by server restart"
                row.last_error = "The previous server process stopped during this download."
                row.completed_at = now
                row.updated_at = now
                attempts = session.scalars(
                    select(JobAttemptRow).where(
                        JobAttemptRow.job_id == row.id,
                        JobAttemptRow.finished_at.is_(None),
                    )
                ).all()
                for attempt in attempts:
                    attempt.finished_at = now
                    attempt.outcome = JobState.INTERRUPTED.value
                    attempt.error_summary = "Server process stopped during the attempt."
                recovered += 1
        return recovered

    def finalize(
        self,
        job_id: str,
        attempt_id: int,
        *,
        state: JobState,
        message: str,
        output_path: str | None = None,
        error: str | None = None,
        exit_code: int | None = None,
    ) -> DownloadJob:
        if state not in TERMINAL_JOB_STATES:
            raise ValueError(f"cannot finalize a job as {state.value}")
        now = self._clock()
        with self._session_factory.begin() as session:
            row = self._require(session, job_id)
            if row.state in TERMINAL_JOB_STATES:
                return _to_domain(row)

            row.state = state.value
            row.status_message = message
            row.updated_at = now
            row.completed_at = now
            row.progress_percent = None
            row.progress_phase = state.value
            if state is JobState.COMPLETED:
                row.output_path = output_path or row.output_path
                row.last_error = None
            elif state in (JobState.FAILED, JobState.INTERRUPTED):
                row.last_error = (error or message)[:500]
            else:
                row.last_error = None

            attempt = session.get(JobAttemptRow, attempt_id)
            if attempt is not None and attempt.finished_at is None:
                attempt.finished_at = now
                attempt.outcome = state.value
                attempt.exit_code = exit_code
                attempt.error_summary = (error or message)[:500]
                attempt.output_path = output_path
            return _to_domain(row)

    def _active_by_key(self, session: Session, track_key: str) -> DownloadJobRow | None:
        return session.scalars(
            select(DownloadJobRow).where(
                DownloadJobRow.track_key == track_key,
                DownloadJobRow.state.in_(_ACTIVE_VALUES),
            )
        ).first()

    @staticmethod
    def _require(session: Session, job_id: str) -> DownloadJobRow:
        row = session.get(DownloadJobRow, job_id)
        if row is None:
            raise JobNotFoundError("Download job not found.")
        return row
