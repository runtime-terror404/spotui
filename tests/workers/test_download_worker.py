from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from spotui.domain.amazon import parse_amazon_track_url
from spotui.domain.jobs import JobState
from spotui.persistence.database import Database
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.providers.downloader.lucidadl import (
    DownloadOutcome,
    DownloadPhase,
    DownloadResult,
)
from spotui.workers.download_worker import DownloadWorker

TRACK_A = parse_amazon_track_url(
    "https://music.amazon.in/albums/B001ALBUM?trackAsin=B002TRACK1"
)
TRACK_B = parse_amazon_track_url(
    "https://music.amazon.in/albums/B001ALBUM?trackAsin=B003TRACK2"
)


class FakeDownloader:
    def __init__(
        self,
        result: DownloadResult | None = None,
        *,
        block: bool = False,
    ) -> None:
        self.result = result or DownloadResult(
            DownloadOutcome.COMPLETED,
            "saved",
            output_path="Artist/Album/Song.flac",
            exit_code=0,
        )
        self.block = block
        self.cancel_event = threading.Event()
        self.started = threading.Event()
        self.run_urls: list[str] = []
        self.cancel_calls: list[float] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def available(self) -> bool:
        return True

    def run(self, url: str, on_phase: Callable[[DownloadPhase], None]) -> DownloadResult:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.run_urls.append(url)
            on_phase(DownloadPhase("downloading", "downloading…"))
            self.started.set()
            if self.block:
                self.cancel_event.wait(5)
            if self.cancel_event.is_set():
                return DownloadResult(DownloadOutcome.CANCELLED, "cancelled")
            return self.result
        finally:
            with self._lock:
                self.active -= 1

    def cancel_active(self, grace_seconds: float) -> None:
        self.cancel_calls.append(grace_seconds)
        self.cancel_event.set()


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


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before the timeout")


def make_worker(
    repository: DownloadJobRepository,
    downloader: FakeDownloader,
    **kwargs,
) -> DownloadWorker:
    return DownloadWorker(
        repository,
        downloader,
        poll_seconds=0.01,
        cancel_grace_seconds=0.1,
        shutdown_grace_seconds=0.1,
        **kwargs,
    )


def test_worker_processes_fifo_one_at_a_time(repository) -> None:
    downloader = FakeDownloader()
    worker = make_worker(repository, downloader)
    first = repository.enqueue(TRACK_A, title="First").job
    second = repository.enqueue(TRACK_B, title="Second").job
    try:
        worker.start()
        wait_until(
            lambda: all(job.state is JobState.COMPLETED for job in repository.list_jobs())
        )
    finally:
        worker.stop()

    assert downloader.run_urls == [first.track_url, second.track_url]
    assert downloader.max_active == 1
    assert all(job.attempt_count == 1 for job in repository.list_jobs())
    assert all(
        job.progress_phase == JobState.COMPLETED.value
        for job in repository.list_jobs()
    )


def test_worker_recovers_active_jobs_without_retrying(repository) -> None:
    interrupted = repository.enqueue(TRACK_A, title="Interrupted").job
    queued = repository.enqueue(TRACK_B, title="Queued").job
    claimed = repository.claim_next()
    assert claimed is not None and claimed.job.id == interrupted.id

    downloader = FakeDownloader()
    worker = make_worker(repository, downloader)
    try:
        worker.start()
        wait_until(lambda: repository.get(queued.id).state is JobState.COMPLETED)
    finally:
        worker.stop()

    assert repository.get(interrupted.id).state is JobState.INTERRUPTED
    assert downloader.run_urls == [queued.track_url]


def test_worker_failure_persists_safe_error(repository) -> None:
    downloader = FakeDownloader(
        DownloadResult(
            DownloadOutcome.FAILED,
            "download failed",
            error="The downloader finished without a success summary.",
        )
    )
    worker = make_worker(repository, downloader)
    job = repository.enqueue(TRACK_A, title="Track").job
    try:
        worker.start()
        wait_until(lambda: repository.get(job.id).state is JobState.FAILED)
    finally:
        worker.stop()

    failed = repository.get(job.id)
    assert failed.last_error == "The downloader finished without a success summary."
    assert failed.completed_at is not None


def test_worker_cancels_active_job(repository) -> None:
    downloader = FakeDownloader(block=True)
    worker = make_worker(repository, downloader)
    job = repository.enqueue(TRACK_A, title="Track").job
    try:
        worker.start()
        assert downloader.started.wait(5)
        repository.request_cancel(job.id)
        worker.cancel_active(job.id)
        wait_until(lambda: repository.get(job.id).state is JobState.CANCELLED)
    finally:
        worker.stop()

    assert downloader.cancel_calls == [0.1]
    assert repository.get(job.id).last_error is None


def test_shutdown_marks_active_job_interrupted_and_keeps_pending(repository) -> None:
    downloader = FakeDownloader(block=True)
    worker = make_worker(repository, downloader)
    active = repository.enqueue(TRACK_A, title="Active").job
    pending = repository.enqueue(TRACK_B, title="Pending").job
    try:
        worker.start()
        assert downloader.started.wait(5)
        worker.stop()
    finally:
        if worker.active_job_id is not None:
            worker.stop()

    assert repository.get(active.id).state is JobState.INTERRUPTED
    assert repository.get(pending.id).state is JobState.QUEUED
    assert downloader.cancel_calls


def test_worker_timeout_marks_job_failed(repository) -> None:
    downloader = FakeDownloader(block=True)
    worker = make_worker(repository, downloader, job_timeout_seconds=0.1)
    job = repository.enqueue(TRACK_A, title="Track").job
    try:
        worker.start()
        assert downloader.started.wait(5)
        wait_until(lambda: repository.get(job.id).state is JobState.FAILED)
    finally:
        worker.stop()

    failed = repository.get(job.id)
    assert failed.status_message == "download timed out"
    assert "timeout" in (failed.last_error or "").lower()


def test_retry_queues_failed_job_for_worker(repository) -> None:
    downloader = FakeDownloader()
    worker = make_worker(repository, downloader)
    job = repository.enqueue(TRACK_A, title="Track").job
    claimed = repository.claim_next()
    assert claimed is not None
    repository.finalize(
        job.id,
        claimed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
    )

    repository.retry(job.id)
    try:
        worker.start()
        wait_until(lambda: repository.get(job.id).state is JobState.COMPLETED)
    finally:
        worker.stop()

    assert repository.get(job.id).attempt_count == 2
