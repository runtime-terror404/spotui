from __future__ import annotations

import pytest

from spotui.domain.amazon import AmazonUrlError, parse_amazon_track_url
from spotui.domain.errors import (
    DownloaderUnavailableError,
    JobTransitionError,
)
from spotui.domain.jobs import DownloadRequest, JobState
from spotui.persistence.database import Database
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.services.queue import QueueService
from tests.fakes import FakeDownloader, FakeLibrary, FakeWorker

TRACK_A = "https://music.amazon.in/albums/B001ALBUM?trackAsin=B002TRACK1"
TRACK_B = "https://music.amazon.in/albums/B001ALBUM?trackAsin=B003TRACK2"
TRACK_C = "https://music.amazon.in/albums/B001ALBUM?trackAsin=B004TRACK3"


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


@pytest.fixture
def worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
def downloader() -> FakeDownloader:
    return FakeDownloader()


def make_service(
    repository: DownloadJobRepository,
    worker: FakeWorker,
    downloader: FakeDownloader,
    library: FakeLibrary | None = None,
) -> QueueService:
    return QueueService(repository, worker, downloader, library=library)


def request(url: str, title: str = "Song", artist: str = "Artist") -> DownloadRequest:
    return DownloadRequest(url=url, title=title, artist=artist)


def test_enqueue_and_duplicate_wake_worker(
    repository, worker, downloader
) -> None:
    service = make_service(repository, worker, downloader)

    first = service.enqueue(request(TRACK_A))
    duplicate = service.enqueue(
        request(parse_amazon_track_url(TRACK_A).canonical_url, title="Other")
    )

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert duplicate.job.id == first.job.id
    assert worker.wakes == 1


def test_enqueue_rejects_invalid_url(repository, worker, downloader) -> None:
    service = make_service(repository, worker, downloader)

    with pytest.raises(AmazonUrlError):
        service.enqueue(request("https://example.com/tracks/B002TRACK1"))


def test_enqueue_requires_downloader(repository, worker, downloader) -> None:
    downloader.available_value = False
    service = make_service(repository, worker, downloader)

    with pytest.raises(DownloaderUnavailableError, match="deps install"):
        service.enqueue(request(TRACK_A))
    assert worker.wakes == 0


def test_batch_counts_invalid_library_and_duplicate(
    repository, worker, downloader
) -> None:
    library = FakeLibrary()
    service = make_service(repository, worker, downloader, library)
    library.in_library = False

    result = service.enqueue_many(
        [
            request(TRACK_A),
            request(TRACK_A),
            request(TRACK_B),
            request("not-a-url"),
        ]
    )

    assert result.added == 2
    assert result.duplicates == 1
    assert result.invalid == 1
    assert result.skipped_library == 0
    assert worker.wakes == 1


def test_batch_skips_library_tracks(repository, worker, downloader) -> None:
    library = FakeLibrary(in_library=True)
    service = make_service(repository, worker, downloader, library)

    result = service.enqueue_many([request(TRACK_A), request(TRACK_B)])

    assert result.added == 0
    assert result.skipped_library == 2
    assert worker.wakes == 0


def test_snapshot_is_ordered_and_counted(repository, worker, downloader) -> None:
    service = make_service(repository, worker, downloader)
    failed = service.enqueue(request(TRACK_A, "Failed")).job
    queued = service.enqueue(request(TRACK_B, "Queued")).job
    active = service.enqueue(request(TRACK_C, "Active")).job

    claimed_failed = repository.claim_next()
    assert claimed_failed is not None
    repository.finalize(
        claimed_failed.job.id,
        claimed_failed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
    )

    claimed_active = repository.claim_next()
    assert claimed_active is not None and claimed_active.job.id == queued.id

    snapshot = service.snapshot()

    assert [job.id for job in snapshot.jobs] == [queued.id, active.id, failed.id]
    assert snapshot.counts.active == 1
    assert snapshot.counts.queued == 1
    assert snapshot.counts.failed == 1


def test_cancel_queued_and_active(repository, worker, downloader) -> None:
    service = make_service(repository, worker, downloader)
    queued = service.enqueue(request(TRACK_A)).job
    active = service.enqueue(request(TRACK_B)).job

    cancelled = service.cancel(queued.id)
    assert cancelled.state is JobState.CANCELLED
    assert worker.cancels == []

    claimed = repository.claim_next()
    assert claimed is not None and claimed.job.id == active.id
    cancelling = service.cancel(active.id)
    assert cancelling.state is JobState.CANCELLING
    assert worker.cancels == [active.id]


def test_cancel_terminal_job_is_invalid(repository, worker, downloader) -> None:
    service = make_service(repository, worker, downloader)
    job = service.enqueue(request(TRACK_A)).job
    service.cancel(job.id)

    with pytest.raises(JobTransitionError):
        service.cancel(job.id)


def test_retry_wakes_worker(repository, worker, downloader) -> None:
    service = make_service(repository, worker, downloader)
    job = service.enqueue(request(TRACK_A)).job
    claimed = repository.claim_next()
    assert claimed is not None
    repository.finalize(
        job.id,
        claimed.attempt_id,
        state=JobState.FAILED,
        message="download failed",
    )

    retried = service.retry(job.id)

    assert retried.state is JobState.QUEUED
    assert worker.wakes == 2  # initial enqueue + retry


def test_start_and_stop_delegate(repository, worker, downloader) -> None:
    service = make_service(repository, worker, downloader)

    service.start()
    service.stop()

    assert worker.started == 1
    assert worker.stopped == 1
