"""Typed API contracts for the download queue."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from spotui.domain.jobs import (
    BatchEnqueueResult,
    DownloadJob,
    EnqueueResult,
    JobState,
    QueueSnapshot,
)


class QueueJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    url: str
    title: str
    artist: str
    state: JobState
    status_message: str
    progress_phase: str | None = None
    progress_percent: float | None = None
    attempt_count: int
    last_error: str | None = None
    output_path: str | None = None
    source_import_id: str | None = None
    source_occurrence_id: str | None = None
    source_playlist_title: str | None = None
    created_at: int
    updated_at: int
    started_at: int | None = None
    completed_at: int | None = None


class QueueCountsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queued: int
    active: int
    completed: int
    failed: int
    cancelled: int
    interrupted: int


class QueueSnapshotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[QueueJobResult]
    counts: QueueCountsResult


class EnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=500)
    artist: str = Field(default="", max_length=500)


class EnqueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: QueueJobResult
    duplicate: bool


class BatchItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=500)
    artist: str = Field(default="", max_length=500)


class BatchEnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BatchItemRequest] = Field(min_length=1, max_length=500)


class BatchEnqueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added: int
    duplicates: int
    skipped_library: int
    invalid: int


def queue_job_result(job: DownloadJob) -> QueueJobResult:
    return QueueJobResult(
        id=job.id,
        url=job.track_url,
        title=job.title,
        artist=job.artist,
        state=job.state,
        status_message=job.status_message,
        progress_phase=job.progress_phase,
        progress_percent=job.progress_percent,
        attempt_count=job.attempt_count,
        last_error=job.last_error,
        output_path=job.output_path,
        source_import_id=job.source_import_id,
        source_occurrence_id=job.source_occurrence_id,
        source_playlist_title=job.source_playlist_title,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def enqueue_response(result: EnqueueResult) -> EnqueueResponse:
    return EnqueueResponse(
        job=queue_job_result(result.job),
        duplicate=result.duplicate,
    )


def queue_snapshot_result(snapshot: QueueSnapshot) -> QueueSnapshotResult:
    return QueueSnapshotResult(
        jobs=[queue_job_result(job) for job in snapshot.jobs],
        counts=QueueCountsResult(
            queued=snapshot.counts.queued,
            active=snapshot.counts.active,
            completed=snapshot.counts.completed,
            failed=snapshot.counts.failed,
            cancelled=snapshot.counts.cancelled,
            interrupted=snapshot.counts.interrupted,
        ),
    )


def batch_result(result: BatchEnqueueResult) -> BatchEnqueueResponse:
    return BatchEnqueueResponse(
        added=result.added,
        duplicates=result.duplicates,
        skipped_library=result.skipped_library,
        invalid=result.invalid,
    )
