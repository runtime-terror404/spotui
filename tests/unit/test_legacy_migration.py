from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from spotui.domain.jobs import JobState
from spotui.domain.legacy import LegacyImportOutcome
from spotui.persistence.database import Database
from spotui.persistence.models import DownloadJob, LegacyQueueImport
from spotui.persistence.repositories.legacy import LegacyQueueRepository
from spotui.services.legacy_migration import (
    LegacyMigrationError,
    LegacyMigrationService,
    parse_legacy_queue,
)


def legacy_job(
    legacy_id: str = "abc12345",
    *,
    status: str = "queued",
    asin: str = "B000000001",
    title: str = "A Song",
    artist: str = "An Artist",
    **extra: object,
) -> dict[str, object]:
    job: dict[str, object] = {
        "id": legacy_id,
        "title": title,
        "artist": artist,
        "url": f"https://music.amazon.com/tracks/{asin}",
        "status": status,
        "message": "legacy message",
        "file": "",
        "added": 1_700_000_000,
        "updated": 1_700_000_100,
    }
    job.update(extra)
    return job


def write_queue(path: Path, jobs: list[object]) -> None:
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


@pytest.fixture
def service(migrated_database_url: str):
    database = Database.from_url(migrated_database_url)
    yield LegacyMigrationService(LegacyQueueRepository(database.session_factory)), database
    database.dispose()


def test_parse_maps_all_legacy_states_and_reports_unsafe_records(
    env, tmp_path: Path
) -> None:
    jobs: list[object] = [
        legacy_job("queued1", status="queued", asin="B000000001"),
        legacy_job("running1", status="running", asin="B000000002"),
        legacy_job("down1", status="downloading", asin="B000000003"),
        legacy_job("done1", status="done", asin="B000000004", file="/music/a.flac"),
        legacy_job("failed1", status="failed", asin="B000000005"),
        legacy_job("cancel1", status="cancelled", asin="B000000006"),
        legacy_job("weird1", status="paused", asin="B000000007"),
        legacy_job("badurl1", status="queued", asin="not-an-asin"),
        {"status": "queued", "url": "https://music.amazon.com/tracks/B000000009"},
    ]
    path = tmp_path / "queue.json"
    write_queue(path, jobs)

    parsed = parse_legacy_queue(path, now=1_800_000_000)

    states = {entry.legacy_id: entry.state for entry in parsed.entries}
    assert states == {
        "queued1": JobState.QUEUED,
        "running1": JobState.INTERRUPTED,
        "down1": JobState.INTERRUPTED,
        "done1": JobState.COMPLETED,
        "failed1": JobState.FAILED,
        "cancel1": JobState.CANCELLED,
    }
    outcomes = {failure.legacy_id: failure.outcome for failure in parsed.failures}
    assert outcomes["weird1"] is LegacyImportOutcome.AMBIGUOUS
    assert outcomes["badurl1"] is LegacyImportOutcome.FAILED
    assert outcomes[None] is LegacyImportOutcome.AMBIGUOUS


def test_dry_run_is_read_only_then_import_is_repeat_safe(service, tmp_path: Path) -> None:
    migration, database = service
    running = legacy_job(
        "run00001",
        status="downloading",
        asin="B000000010",
        title="Interrupted Song",
    )
    completed = legacy_job(
        "done0001",
        status="done",
        asin="B000000011",
        file="/music/Done.flac",
    )
    failed = legacy_job(
        "fail0001",
        status="failed",
        asin="B000000012",
        message="rip failed — retry?",
    )
    queued = legacy_job("queue001", status="queued", asin="B000000013")
    ambiguous = legacy_job("pause001", status="paused", asin="B000000014")
    path = tmp_path / "queue.json"
    write_queue(path, [running, completed, failed, queued, ambiguous])
    original = path.read_bytes()

    preview = migration.migrate(path, dry_run=True)

    assert preview.imported == 4
    assert preview.ambiguous == 1
    with database.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(DownloadJob)) == 0
        assert session.scalar(select(func.count()).select_from(LegacyQueueImport)) == 0
    assert path.read_bytes() == original

    first = migration.migrate(path)
    assert (first.imported, first.skipped, first.ambiguous, first.failed) == (4, 0, 1, 0)
    assert path.read_bytes() == original

    with database.session_scope() as session:
        rows = {
            row.track_key: row
            for row in session.scalars(select(DownloadJob)).all()
        }
        assert len(rows) == 4
        interrupted_row = rows["amazon:B000000010"]
        assert interrupted_row.state == JobState.INTERRUPTED.value
        assert "not resumed" in interrupted_row.status_message
        assert interrupted_row.started_at == 1_700_000_000
        assert interrupted_row.completed_at == 1_700_000_100
        completed_row = rows["amazon:B000000011"]
        assert completed_row.state == JobState.COMPLETED.value
        assert completed_row.output_path == "/music/Done.flac"
        failed_row = rows["amazon:B000000012"]
        assert failed_row.state == JobState.FAILED.value
        assert failed_row.last_error == "rip failed — retry?"
        queued_row = rows["amazon:B000000013"]
        assert queued_row.state == JobState.QUEUED.value
        assert queued_row.attempt_count == 0
        assert session.scalar(select(func.count()).select_from(LegacyQueueImport)) == 5

    second = migration.migrate(path)
    assert second.imported == 0
    assert second.skipped == 5
    assert second.ambiguous == 0
    assert any(
        "already processed as imported" in (result.reason or "")
        for result in second.results
    )
    with database.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(DownloadJob)) == 4
        assert session.scalar(select(func.count()).select_from(LegacyQueueImport)) == 5


def test_running_jobs_never_return_to_queued(service, tmp_path: Path) -> None:
    migration, database = service
    path = tmp_path / "queue.json"
    write_queue(path, [legacy_job("run00002", status="running")])

    report = migration.migrate(path)

    assert report.imported == 1
    with database.session_scope() as session:
        row = session.scalar(select(DownloadJob))
        assert row is not None
        assert row.state == JobState.INTERRUPTED.value


def test_queued_duplicate_of_existing_active_job_is_skipped(
    service, tmp_path: Path
) -> None:
    migration, database = service
    with database.session_scope() as session:
        session.add(
            DownloadJob(
                id="activejob0000000000000000000001",
                track_url="https://music.amazon.com/tracks/B000000020",
                track_key="amazon:B000000020",
                title="Already active",
                artist="",
                state=JobState.QUEUED.value,
                status_message="queued",
                attempt_count=0,
                created_at=1_700_000_000,
                updated_at=1_700_000_000,
            )
        )
    path = tmp_path / "queue.json"
    write_queue(
        path,
        [legacy_job("dupe0001", status="queued", asin="B000000020")],
    )

    report = migration.migrate(path)

    assert report.imported == 0
    assert report.skipped == 1
    assert report.results[0].job_id == "activejob0000000000000000000001"
    with database.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(DownloadJob)) == 1
        ledger = session.scalar(select(LegacyQueueImport))
        assert ledger is not None
        assert ledger.outcome == LegacyImportOutcome.SKIPPED.value
        assert ledger.job_id == "activejob0000000000000000000001"


def test_malformed_legacy_queue_fails_without_writing(service, tmp_path: Path) -> None:
    migration, database = service
    path = tmp_path / "queue.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(LegacyMigrationError, match="cannot read legacy queue"):
        migration.migrate(path)

    with database.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(LegacyQueueImport)) == 0
