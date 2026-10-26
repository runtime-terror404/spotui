from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from spotui.domain.jobs import ACTIVE_JOB_STATES, JobState
from spotui.persistence.database import Database
from spotui.persistence.models import DownloadJob


@pytest.fixture
def database(migrated_database_url: str):
    instance = Database.from_url(migrated_database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def make_job(
    job_id: str = "job-1",
    *,
    track_key: str = "B000000001",
    state: JobState | str = JobState.QUEUED,
    **overrides: Any,
) -> DownloadJob:
    values = {
        "id": job_id,
        "track_url": f"https://music.amazon.com/tracks/{track_key}",
        "track_key": track_key,
        "title": "A Song",
        "artist": "An Artist",
        "state": state.value if isinstance(state, JobState) else state,
        "status_message": "queued",
        "attempt_count": 0,
        "created_at": 1_700_000_000,
        "updated_at": 1_700_000_000,
    }
    values.update(overrides)
    return DownloadJob(**values)


def insert(database: Database, *jobs: DownloadJob) -> None:
    with database.session_scope() as session:
        session.add_all(jobs)


@pytest.mark.parametrize("active_state", sorted(ACTIVE_JOB_STATES, key=lambda item: item.value))
def test_duplicate_active_track_key_is_blocked(database: Database, active_state: JobState) -> None:
    insert(database, make_job("job-1", state=active_state))

    with pytest.raises(IntegrityError):
        insert(database, make_job("job-2", state=JobState.QUEUED))


@pytest.mark.parametrize(
    "terminal_state",
    [
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.INTERRUPTED,
    ],
)
def test_re_download_after_terminal_state_is_allowed(
    database: Database, terminal_state: JobState
) -> None:
    insert(database, make_job("job-1", state=terminal_state))

    insert(database, make_job("job-2", state=JobState.QUEUED))

    with database.session_scope() as session:
        assert session.query(DownloadJob).count() == 2


def test_same_active_key_for_different_tracks_is_allowed(database: Database) -> None:
    insert(
        database,
        make_job("job-1", track_key="B000000001"),
        make_job("job-2", track_key="B000000002"),
    )

    with database.session_scope() as session:
        assert session.query(DownloadJob).count() == 2


def test_two_completed_jobs_may_share_a_track_key(database: Database) -> None:
    insert(
        database,
        make_job("job-1", state=JobState.COMPLETED),
        make_job("job-2", state=JobState.COMPLETED),
    )

    with database.session_scope() as session:
        assert session.query(DownloadJob).count() == 2


def test_transition_into_active_state_respects_uniqueness(database: Database) -> None:
    insert(
        database,
        make_job("job-1", state=JobState.COMPLETED),
        make_job("job-2", state=JobState.RUNNING),
    )

    with pytest.raises(IntegrityError):
        with database.session_scope() as session:
            job = session.get(DownloadJob, "job-1")
            assert job is not None
            job.state = JobState.RUNNING.value


def test_invalid_state_is_rejected(database: Database) -> None:
    with pytest.raises(IntegrityError):
        insert(database, make_job(state="bogus"))


def test_negative_attempt_count_is_rejected(database: Database) -> None:
    with pytest.raises(IntegrityError):
        insert(database, make_job(attempt_count=-1))


@pytest.mark.parametrize("percent", [-1, 100.5])
def test_progress_percent_out_of_range_is_rejected(database: Database, percent: float) -> None:
    with pytest.raises(IntegrityError):
        insert(database, make_job(progress_percent=percent))


def test_progress_percent_can_be_absent(database: Database) -> None:
    insert(database, make_job(progress_percent=None))

    with database.session_scope() as session:
        assert session.get(DownloadJob, "job-1").progress_percent is None


def test_active_unique_index_is_partial(database: Database) -> None:
    inspector = inspect(database.engine)
    indexes = {index["name"]: index for index in inspector.get_indexes("download_jobs")}

    index = indexes["ux_download_jobs_active_track_key"]
    assert index["unique"] == 1
    assert index["column_names"] == ["track_key"]
    assert index["dialect_options"]["sqlite_where"] is not None
