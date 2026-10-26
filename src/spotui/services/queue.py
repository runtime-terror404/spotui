"""Download queue use cases."""

from __future__ import annotations

from collections.abc import Iterable

from spotui.domain.amazon import AmazonUrlError, parse_amazon_track_url
from spotui.domain.errors import DownloaderUnavailableError
from spotui.domain.jobs import (
    BatchEnqueueResult,
    DownloadJob,
    DownloadRequest,
    EnqueueResult,
    JobState,
    QueueSnapshot,
)
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.providers.downloader.lucidadl import Downloader
from spotui.providers.library.base import LibraryLookup
from spotui.workers.download_worker import DownloadWorker

_PRIORITY = {
    JobState.STARTING: 0,
    JobState.RUNNING: 0,
    JobState.CANCELLING: 0,
    JobState.QUEUED: 1,
    JobState.FAILED: 2,
    JobState.INTERRUPTED: 2,
    JobState.COMPLETED: 3,
    JobState.CANCELLED: 3,
}


class QueueService:
    def __init__(
        self,
        repository: DownloadJobRepository,
        worker: DownloadWorker,
        downloader: Downloader,
        *,
        library: LibraryLookup | None = None,
    ) -> None:
        self._repository = repository
        self._worker = worker
        self._downloader = downloader
        self._library = library

    def start(self) -> None:
        self._worker.start()

    def stop(self) -> None:
        self._worker.stop()

    def enqueue(self, request: DownloadRequest) -> EnqueueResult:
        self._require_downloader()
        track = parse_amazon_track_url(request.url)
        result = self._repository.enqueue(
            track,
            title=request.title,
            artist=request.artist,
            source_import_id=request.source_import_id,
            source_occurrence_id=request.source_occurrence_id,
            source_playlist_title=request.source_playlist_title,
        )
        if not result.duplicate:
            self._worker.wake()
        return result

    def enqueue_many(self, requests: Iterable[DownloadRequest]) -> BatchEnqueueResult:
        self._require_downloader()
        added = duplicates = skipped_library = invalid = 0
        for request in requests:
            try:
                track = parse_amazon_track_url(request.url)
            except AmazonUrlError:
                invalid += 1
                continue
            if self._library is not None and self._library.lookup(
                request.url,
                request.title,
                request.artist,
            ).match is not None:
                skipped_library += 1
                continue
            result = self._repository.enqueue(
                track,
                title=request.title,
                artist=request.artist,
                source_import_id=request.source_import_id,
                source_occurrence_id=request.source_occurrence_id,
                source_playlist_title=request.source_playlist_title,
            )
            if result.duplicate:
                duplicates += 1
            else:
                added += 1
        if added:
            self._worker.wake()
        return BatchEnqueueResult(
            added=added,
            duplicates=duplicates,
            skipped_library=skipped_library,
            invalid=invalid,
        )

    def snapshot(self) -> QueueSnapshot:
        jobs = self._repository.list_jobs()

        def order(job: DownloadJob) -> tuple[int, int]:
            priority = _PRIORITY.get(job.state, 99)
            if priority <= 1:
                return priority, job.created_at
            return priority, -job.updated_at

        ordered = tuple(sorted(jobs, key=order))
        return QueueSnapshot(jobs=ordered, counts=self._repository.counts())

    def get(self, job_id: str) -> DownloadJob:
        return self._repository.get(job_id)

    def cancel(self, job_id: str) -> DownloadJob:
        job = self._repository.request_cancel(job_id)
        if job.state is JobState.CANCELLING:
            self._worker.cancel_active(job_id)
        return self._repository.get(job_id)

    def retry(self, job_id: str) -> DownloadJob:
        self._require_downloader()
        job = self._repository.retry(job_id)
        self._worker.wake()
        return job

    def ensure_available(self) -> None:
        if not self._downloader.available():
            raise DownloaderUnavailableError(
                "The managed lucidadl downloader is not installed. "
                "Run 'spotui deps install'."
            )

    def _require_downloader(self) -> None:
        self.ensure_available()
