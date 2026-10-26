from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from spotui.domain.amazon import parse_amazon_track_url
from spotui.domain.errors import (
    DuplicateActiveJobError,
    JobNotFoundError,
    JobTransitionError,
)
from spotui.domain.jobs import JobState
from spotui.persistence.database import Database
from spotui.persistence.models import JobAttempt as JobAttemptRow
from spotui.persistence.repositories.download_jobs import DownloadJobRepository

TRACK_A = parse_amazon_track_url(
    "https://music.amazon.in/albums/B001ALBUM?trackAsin=B002TRACK1"
)
TRACK_B = parse_amazon_track_url(
    "https://music.amazon.in/albums/B001ALBUM?trackAsin=B003TRACK2"
)


class TickClock:
    def __init__(self) -> None:
        self.value = 1_700_000_000

    def __call__(self) -> int:
        self.value += 1
        return self.value


@pytest.fixture
def database(migrated_database_url: str):
    instance = Database.from_url(migrated_database_url)
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture
def repository(database: Database) -> DownloadJobRepository:
    return DownloadJobRepository(database.session_factory, clock=TickClock())


def enqueue(repository: DownloadJobRepository, track=TRACK_A, title="Song", artist="Artist"):
    return repository.enqueue(track, title=title, artist=artist)


def attempts(database: Database, job_id: str) -> list[JobAttemptRow]:
    with database.session_scope() as session:
        return list(
            session.scalars(
                select(JobAttemptRow)
                .where(JobAttemptRow.job_id == job_id)
                .order_by(JobAttemptRow.attempt_number)
            ).all()
        )


def test_enqueue_is_idempotent_for_active_track_identity(repository) -> None:
    first = enqueue(repository)
    duplicate = repository.enqueue(
        parse_amazon_track_url("https://music.amazon.com/tracks/B002TRACK1"),
        title="Other title",
    )
    other = enqueue(repository, track=TRACK_B, title="Other song")

    assert first.duplicate is False
    assert first.job.state is JobState.QUEUED
    assert duplicate.duplicate is True
    assert duplicate.job.id == first.job.id
    assert other.duplicate is False
    assert repository.counts().queued == 2


def test_title_falls_back_to_url(repository) -> None:
    result = enqueue(repository, title="   ")

    assert result.job.title == TRACK_A.original


def test_claim_is_fifo_and_creates_attempt(repository, database: Database) -> None:
    first = enqueue(repository, title="First").job
    enqueue(repository, track=TRACK_B, title="Second")

    claimed = repository.claim_next()

    assert claimed is not None
    assert claimed.job.id == first.id
    assert claimed.job.state is JobState.STARTING
    assert claimed.job.attempt_count == 1
    rows = attempts(database, first.id)
    assert len(rows) == 1
    assert rows[0].attempt_number == 1
    assert rows[0].finished_at is None

    assert repository.claim_next() is not None
    assert repository.claim_next() is None


def test_enqueue_is_duplicate_while_claimed_job_is_active(repository) -> None:
    job = enqueue(repository).job
    repository.claim_next()

    duplicate = enqueue(repository)

    assert duplicate.duplicate is True
    assert duplicate.job.id == job.id


def test_progress_and_running_transitions(repository) -> None:
    job = enqueue(repository).job
    claimed = repository.claim_next()
    assert claimed is not None

    running = repository.mark_running(job.id, message="starting…", phase="starting")
    updated = repository.update_progress(
        job.id,
        phase="downloading",
        message="downloading…",
    )

    assert running.state is JobState.RUNNING
    assert updated is not None
    assert updated.state is JobState.RUNNING
    assert updated.progress_phase == "downloading"
    assert updated.progress_percent is None


def test_cancel_queued_job(repository) -> None:
    job = enqueue(repository).job

    cancelled = repository.request_cancel(job.id)

    assert cancelled.state is JobState.CANCELLED
    assert cancelled.completed_at is not None
    assert repository.counts().cancelled == 1


def test_cancel_active_job_requests_cancelling(repository) -> None:
    job = enqueue(repository).job
    claimed = repository.claim_next()
    assert claimed is not None
    repository.mark_running(job.id, message="starting…", phase="starting")

    cancelling = repository.request_cancel(job.id)

    assert cancelling.state is JobState.CANCELLING
    assert repository.request_cancel(job.id).state is JobState.CANCELLING

    final = repository.finalize(
        job.id,
        claimed.attempt_id,
        state=JobState.CANCELLED,
        message="cancelled",
    )
    assert final.state is JobState.CANCELLED


def test_finalize_completed_records_attempt_and_output(repository, database: Database) -> None:
    job = enqueue(repository).job
    claimed = repository.claim_next()
    assert claimed is not None

    completed = repository.finalize(
        job.id,
        claimed.attempt_id,
        state=JobState.COMPLETED,
        message="saved",
        output_path="Artist/Album/Song.flac",
        exit_code=0,
    )

    assert completed.state is JobState.COMPLETED
    assert completed.output_path == "Artist/Album/Song.flac"
    assert completed.completed_at is not None
    rows = attempts(database, job.id)
    assert rows[0].outcome == JobState.COMPLETED.value
    assert rows[0].exit_code == 0
    assert rows[0].output_path == "Artist/Album/Song.flac"


def test_retry_failed_job(repository) -> None:
    job = enqueue(repository).job
    claimed = repository.claim_next()
    assert claimed is not None
    repository.finalize(
        job.id,
        claimed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
        error="boom",
    )

    retried = repository.retry(job.id)

    assert retried.state is JobState.QUEUED
    assert retried.attempt_count == 1
    assert retried.last_error is None
    claimed_again = repository.claim_next()
    assert claimed_again is not None
    assert claimed_again.job.attempt_count == 2


def test_retry_respects_active_identity_conflict(repository) -> None:
    failed = enqueue(repository).job
    claimed = repository.claim_next()
    assert claimed is not None
    repository.finalize(
        failed.id,
        claimed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
    )
    replacement = enqueue(repository).job
    assert replacement.id != failed.id

    with pytest.raises(DuplicateActiveJobError):
        repository.retry(failed.id)

    assert repository.get(failed.id).state is JobState.FAILED


def test_retry_only_failed_or_interrupted(repository) -> None:
    job = enqueue(repository).job

    with pytest.raises(JobTransitionError):
        repository.retry(job.id)


def test_recovery_marks_active_interrupted_and_keeps_queued(repository, database: Database) -> None:
    active = enqueue(repository, title="Active").job
    queued = enqueue(repository, track=TRACK_B, title="Queued").job
    claimed = repository.claim_next()
    assert claimed is not None and claimed.job.id == active.id

    recovered = repository.recover_interrupted()

    assert recovered == 1
    assert repository.get(active.id).state is JobState.INTERRUPTED
    assert repository.get(queued.id).state is JobState.QUEUED
    rows = attempts(database, active.id)
    assert rows[0].outcome == JobState.INTERRUPTED.value
    assert rows[0].finished_at is not None


def test_missing_job_is_reported(repository) -> None:
    with pytest.raises(JobNotFoundError):
        repository.get("missing")
    with pytest.raises(JobNotFoundError):
        repository.request_cancel("missing")
    with pytest.raises(JobNotFoundError):
        repository.retry("missing")


def test_attempt_unique_number_is_enforced(database: Database) -> None:
    repository = DownloadJobRepository(database.session_factory, clock=TickClock())
    job = enqueue(repository).job
    repository.claim_next()

    with pytest.raises(IntegrityError):
        with database.session_scope() as session:
            session.add(
                JobAttemptRow(
                    job_id=job.id,
                    attempt_number=1,
                    started_at=1,
                )
            )
