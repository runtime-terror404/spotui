from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from spotui.app import create_app
from spotui.domain.jobs import JobState
from spotui.persistence.database import Database
from spotui.persistence.models import JobAttempt
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.runtime import ApplicationRuntime
from spotui.schemas.errors import ErrorCode
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.queue import QueueService
from spotui.services.search import SearchService
from tests.api.helpers import CSRFTestClient as TestClient
from tests.api.helpers import assert_problem
from tests.fakes import (
    FakeCatalog,
    FakeDownloader,
    FakeLibrary,
    FakeWorker,
)

TRACK_A = "https://music.amazon.in/albums/B001ALBUM?trackAsin=B002TRACK1"
TRACK_B = "https://music.amazon.in/albums/B001ALBUM?trackAsin=B003TRACK2"
TRACK_C = "https://music.amazon.in/albums/B001ALBUM?trackAsin=B004TRACK3"


class TickClock:
    def __init__(self) -> None:
        self.value = 1_700_000_000

    def __call__(self) -> int:
        self.value += 1
        return self.value


@dataclass
class QueueContext:
    client: TestClient
    app: FastAPI
    database: Database
    repository: DownloadJobRepository
    queue: QueueService
    worker: FakeWorker
    downloader: FakeDownloader
    library: FakeLibrary


@pytest.fixture
def queue_context(
    env,
    runtime: ApplicationRuntime,
    migrated_database_url: str,
    fake_catalog: FakeCatalog,
) -> Iterator[QueueContext]:
    database = Database.from_url(migrated_database_url)
    repository = DownloadJobRepository(database.session_factory, clock=TickClock())
    worker = FakeWorker()
    downloader = FakeDownloader()
    library = FakeLibrary()
    queue = QueueService(repository, worker, downloader, library=library)
    runtime.services = ApplicationServices(
        search=SearchService(fake_catalog),
        entity_details=EntityDetailsService(fake_catalog),
        queue=queue,
        resources=(),
    )
    app = create_app(runtime, serve_frontend=False)
    try:
        with TestClient(app) as client:
            yield QueueContext(
                client=client,
                app=app,
                database=database,
                repository=repository,
                queue=queue,
                worker=worker,
                downloader=downloader,
                library=library,
            )
    finally:
        database.dispose()


def test_empty_queue(queue_context: QueueContext) -> None:
    response = queue_context.client.get("/api/v1/queue")

    assert response.status_code == 200
    body = response.json()
    assert body["jobs"] == []
    assert body["counts"] == {
        "queued": 0,
        "active": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "interrupted": 0,
    }


def test_enqueue_is_idempotent(queue_context: QueueContext) -> None:
    first = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Song", "artist": "Artist"},
    )
    second = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Other", "artist": "Artist"},
    )

    assert first.status_code == 201
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["duplicate"] is False
    assert second_body["duplicate"] is True
    assert first_body["job"]["id"] == second_body["job"]["id"]
    assert first_body["job"]["state"] == "queued"
    assert first_body["job"]["url"] == TRACK_A

    snapshot = queue_context.client.get("/api/v1/queue").json()
    assert len(snapshot["jobs"]) == 1
    assert snapshot["counts"]["queued"] == 1
    job = queue_context.client.get(
        f"/api/v1/queue/jobs/{first_body['job']['id']}"
    )
    assert job.status_code == 200
    assert job.json()["id"] == first_body["job"]["id"]


def test_enqueue_invalid_url(queue_context: QueueContext) -> None:
    response = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": "https://example.com/tracks/B002TRACK1", "title": "Song"},
    )

    assert_problem(response, 400, ErrorCode.INVALID_URL)


def test_enqueue_without_downloader(queue_context: QueueContext) -> None:
    queue_context.downloader.available_value = False

    response = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Song"},
    )

    body = assert_problem(response, 503, ErrorCode.DOWNLOADER_UNAVAILABLE)
    assert "deps install" in body["detail"]


def test_batch_counts_and_validation(queue_context: QueueContext) -> None:
    response = queue_context.client.post(
        "/api/v1/queue/batch",
        json={
            "items": [
                {"url": TRACK_A, "title": "One"},
                {"url": TRACK_A, "title": "Duplicate"},
                {"url": TRACK_B, "title": "Two"},
                {"url": "not-a-url", "title": "Invalid"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "added": 2,
        "duplicates": 1,
        "skipped_library": 0,
        "invalid": 1,
    }

    empty = queue_context.client.post("/api/v1/queue/batch", json={"items": []})
    assert_problem(empty, 422, ErrorCode.VALIDATION_ERROR)


def test_batch_skips_library(queue_context: QueueContext) -> None:
    queue_context.library.in_library = True

    response = queue_context.client.post(
        "/api/v1/queue/batch",
        json={"items": [{"url": TRACK_A}, {"url": TRACK_B}]},
    )

    assert response.status_code == 200
    assert response.json()["added"] == 0
    assert response.json()["skipped_library"] == 2


def test_get_missing_job(queue_context: QueueContext) -> None:
    response = queue_context.client.get("/api/v1/queue/jobs/missing")

    assert_problem(response, 404, ErrorCode.JOB_NOT_FOUND)


def test_cancel_queued_and_active_jobs(queue_context: QueueContext) -> None:
    queued = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Queued"},
    ).json()["job"]
    active = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_B, "title": "Active"},
    ).json()["job"]

    cancelled = queue_context.client.post(
        f"/api/v1/queue/jobs/{queued['id']}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert queue_context.worker.cancels == []

    claimed = queue_context.repository.claim_next()
    assert claimed is not None and claimed.job.id == active["id"]
    cancelling = queue_context.client.post(
        f"/api/v1/queue/jobs/{active['id']}/cancel"
    )
    assert cancelling.status_code == 200
    assert cancelling.json()["state"] == "cancelling"
    assert queue_context.worker.cancels == [active["id"]]

    again = queue_context.client.post(f"/api/v1/queue/jobs/{queued['id']}/cancel")
    assert_problem(again, 409, ErrorCode.INVALID_TRANSITION)


def test_dismiss_queued_job_removes_it_without_history(
    queue_context: QueueContext,
) -> None:
    job = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Queued"},
    ).json()["job"]

    response = queue_context.client.delete(f"/api/v1/queue/jobs/{job['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert_problem(
        queue_context.client.get(f"/api/v1/queue/jobs/{job['id']}"),
        404,
        ErrorCode.JOB_NOT_FOUND,
    )
    snapshot = queue_context.client.get("/api/v1/queue").json()
    assert snapshot["jobs"] == []
    assert snapshot["counts"]["queued"] == 0
    assert snapshot["counts"]["cancelled"] == 0


def test_dismiss_failed_job_removes_attempt_history(
    queue_context: QueueContext,
) -> None:
    job = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Failed"},
    ).json()["job"]
    claimed = queue_context.repository.claim_next()
    assert claimed is not None
    queue_context.repository.finalize(
        job["id"],
        claimed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
    )

    response = queue_context.client.delete(f"/api/v1/queue/jobs/{job['id']}")

    assert response.status_code == 204
    with queue_context.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 0
    snapshot = queue_context.client.get("/api/v1/queue").json()
    assert snapshot["jobs"] == []
    assert snapshot["counts"]["failed"] == 0


def test_dismiss_active_or_missing_job_is_rejected(
    queue_context: QueueContext,
) -> None:
    job = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Active"},
    ).json()["job"]
    assert queue_context.repository.claim_next() is not None

    assert_problem(
        queue_context.client.delete(f"/api/v1/queue/jobs/{job['id']}"),
        409,
        ErrorCode.INVALID_TRANSITION,
    )
    assert_problem(
        queue_context.client.delete("/api/v1/queue/jobs/missing"),
        404,
        ErrorCode.JOB_NOT_FOUND,
    )


def test_retry_failed_job_and_invalid_transition(queue_context: QueueContext) -> None:
    job = queue_context.client.post(
        "/api/v1/queue/jobs",
        json={"url": TRACK_A, "title": "Song"},
    ).json()["job"]
    claimed = queue_context.repository.claim_next()
    assert claimed is not None
    queue_context.repository.finalize(
        job["id"],
        claimed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
    )

    retried = queue_context.client.post(f"/api/v1/queue/jobs/{job['id']}/retry")

    assert retried.status_code == 200
    assert retried.json()["state"] == "queued"
    assert queue_context.worker.wakes >= 2

    invalid = queue_context.client.post(f"/api/v1/queue/jobs/{job['id']}/retry")
    assert_problem(invalid, 409, ErrorCode.INVALID_TRANSITION)


def test_queue_requires_services(client) -> None:
    response = client.get("/api/v1/queue")

    assert_problem(response, 503, ErrorCode.DOWNLOADER_UNAVAILABLE)
