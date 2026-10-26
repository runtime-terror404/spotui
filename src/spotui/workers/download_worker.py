"""Single-threaded download worker with explicit cancellation and recovery."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from spotui.domain.errors import JobNotFoundError
from spotui.domain.jobs import ClaimedJob, DownloadJob, JobState
from spotui.logging_setup import log_context
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.providers.downloader.lucidadl import (
    Downloader,
    DownloadOutcome,
    DownloadPhase,
    DownloadResult,
)

logger = logging.getLogger("spotui.worker.download")


class DownloadWorker:
    def __init__(
        self,
        repository: DownloadJobRepository,
        downloader: Downloader,
        *,
        cancel_grace_seconds: float = 5.0,
        shutdown_grace_seconds: float = 5.0,
        job_timeout_seconds: float = 900.0,
        poll_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repository = repository
        self._downloader = downloader
        self._cancel_grace = cancel_grace_seconds
        self._shutdown_grace = shutdown_grace_seconds
        self._job_timeout = job_timeout_seconds
        self._poll_seconds = poll_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._active_done = threading.Event()
        self._active_done.set()
        self._thread: threading.Thread | None = None
        self._active_job_id: str | None = None
        self._active_attempt_id: int | None = None
        self._shutdown_requested = False
        self._timeout_requested = False

    @property
    def active_job_id(self) -> str | None:
        with self._lock:
            return self._active_job_id

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopping.clear()
            self._shutdown_requested = False
            self._timeout_requested = False
        recovered = self._repository.recover_interrupted()
        if recovered:
            logger.warning("marked %d interrupted download job(s)", recovered)
        self._thread = threading.Thread(
            target=self._loop,
            name="download-worker",
            daemon=True,
        )
        self._thread.start()
        self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def cancel_active(self, job_id: str) -> None:
        with self._lock:
            if self._active_job_id != job_id:
                return
        self._downloader.cancel_active(self._cancel_grace)

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        thread = self._thread
        if thread is None:
            return

        active = not self._active_done.is_set()
        if active and not self._active_done.wait(self._shutdown_grace):
            with self._lock:
                self._shutdown_requested = True
            self._downloader.cancel_active(self._cancel_grace)

        thread.join(timeout=self._shutdown_grace + self._cancel_grace + 10.0)
        if thread.is_alive():
            logger.error("download worker did not stop within the shutdown grace period")
        else:
            self._thread = None
        self._wake.set()

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                claimed = self._repository.claim_next()
            except Exception:
                logger.exception("failed to claim the next download job")
                self._wake.wait(self._poll_seconds)
                self._wake.clear()
                continue
            if claimed is None:
                self._wake.wait(self._poll_seconds)
                self._wake.clear()
                continue

            with self._lock:
                self._active_job_id = claimed.job.id
                self._active_attempt_id = claimed.attempt_id
                self._shutdown_requested = False
                self._timeout_requested = False
                self._active_done.clear()
            try:
                self._run_claimed(claimed)
            except Exception:
                logger.exception("download worker failed while processing a job")
                self._fail_safely(claimed)
            finally:
                with self._lock:
                    self._active_job_id = None
                    self._active_attempt_id = None
                self._active_done.set()

    def _run_claimed(self, claimed: ClaimedJob) -> None:
        job = claimed.job
        with log_context(job_id=job.id):
            try:
                current = self._repository.get(job.id)
            except JobNotFoundError:
                return
            if current.state is JobState.CANCELLING:
                self._repository.finalize(
                    job.id,
                    claimed.attempt_id,
                    state=JobState.CANCELLED,
                    message="cancelled",
                )
                return
            if self._stopping.is_set():
                self._repository.finalize(
                    job.id,
                    claimed.attempt_id,
                    state=JobState.INTERRUPTED,
                    message="interrupted by shutdown",
                    error="SpotUI shut down before the download started.",
                )
                return

            self._repository.mark_running(
                job.id,
                message="starting…",
                phase="starting",
            )
            logger.info("download started: %s — %s", job.title, job.artist)
            done = threading.Event()
            timer = threading.Timer(
                self._job_timeout,
                self._timeout_job,
                args=(job.id, done),
            )
            timer.daemon = True
            timer.start()
            try:
                result = self._downloader.run(
                    job.track_url,
                    self._phase_callback(job.id),
                )
            except Exception:
                logger.exception("downloader failed to start or run")
                result = DownloadResult(
                    DownloadOutcome.FAILED,
                    "download failed",
                    error="The downloader could not be started.",
                )
            finally:
                done.set()
                timer.cancel()

            self._finalize(job, claimed.attempt_id, result)

    def _phase_callback(self, job_id: str):
        def update(phase: DownloadPhase) -> None:
            self._repository.update_progress(
                job_id,
                phase=phase.name,
                message=phase.message,
                percent=phase.percent,
            )

        return update

    def _timeout_job(self, job_id: str, done: threading.Event) -> None:
        if done.is_set():
            return
        with self._lock:
            if self._active_job_id != job_id:
                return
            self._timeout_requested = True
        logger.warning("download job exceeded the configured timeout")
        self._downloader.cancel_active(self._cancel_grace)

    def _finalize(self, job: DownloadJob, attempt_id: int, result: DownloadResult) -> None:
        with self._lock:
            shutdown = self._shutdown_requested
            timed_out = self._timeout_requested
        try:
            current = self._repository.get(job.id)
        except JobNotFoundError:
            return

        if shutdown:
            state = JobState.INTERRUPTED
            message = "interrupted by shutdown"
            error = "SpotUI shut down while this download was active."
        elif timed_out:
            state = JobState.FAILED
            message = "download timed out"
            error = "The downloader exceeded the configured job timeout."
        elif result.outcome is DownloadOutcome.CANCELLED or current.state is JobState.CANCELLING:
            state = JobState.CANCELLED
            message = "cancelled"
            error = None
        elif result.outcome is DownloadOutcome.COMPLETED:
            state = JobState.COMPLETED
            message = result.message
            error = None
        else:
            state = JobState.FAILED
            message = result.message
            error = result.error or "The download failed."

        finalized = self._repository.finalize(
            job.id,
            attempt_id,
            state=state,
            message=message,
            output_path=result.output_path,
            error=error,
            exit_code=result.exit_code,
        )
        logger.info(
            "download finished: %s (%s)",
            finalized.title,
            finalized.state.value,
        )

    def _fail_safely(self, claimed: ClaimedJob) -> None:
        try:
            current = self._repository.get(claimed.job.id)
            if current.state in (
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.INTERRUPTED,
            ):
                return
            self._repository.finalize(
                claimed.job.id,
                claimed.attempt_id,
                state=JobState.FAILED,
                message="download failed",
                error="An unexpected worker error occurred.",
            )
        except Exception:
            logger.exception("failed to persist a safe terminal state")
