from __future__ import annotations

from fastapi import APIRouter, Response

from spotui.api.v1.dependencies import QueueDependency
from spotui.domain.jobs import DownloadRequest
from spotui.schemas.queue import (
    BatchEnqueueRequest,
    BatchEnqueueResponse,
    EnqueueRequest,
    EnqueueResponse,
    QueueJobResult,
    QueueSnapshotResult,
    batch_result,
    enqueue_response,
    queue_job_result,
    queue_snapshot_result,
)

router = APIRouter()


@router.get("/queue", response_model=QueueSnapshotResult, summary="List download jobs")
def list_queue(queue: QueueDependency) -> QueueSnapshotResult:
    return queue_snapshot_result(queue.snapshot())


@router.post(
    "/queue/jobs",
    response_model=EnqueueResponse,
    status_code=201,
    summary="Enqueue one Amazon track",
)
def enqueue_job(
    body: EnqueueRequest,
    queue: QueueDependency,
    response: Response,
) -> EnqueueResponse:
    result = queue.enqueue(
        DownloadRequest(url=body.url, title=body.title, artist=body.artist)
    )
    if result.duplicate:
        response.status_code = 200
    return enqueue_response(result)


@router.post(
    "/queue/batch",
    response_model=BatchEnqueueResponse,
    summary="Enqueue multiple Amazon tracks",
)
def enqueue_batch(
    body: BatchEnqueueRequest,
    queue: QueueDependency,
) -> BatchEnqueueResponse:
    result = queue.enqueue_many(
        DownloadRequest(url=item.url, title=item.title, artist=item.artist)
        for item in body.items
    )
    return batch_result(result)


@router.get(
    "/queue/jobs/{job_id}",
    response_model=QueueJobResult,
    summary="Get one download job",
)
def get_job(job_id: str, queue: QueueDependency) -> QueueJobResult:
    return queue_job_result(queue.get(job_id))


@router.post(
    "/queue/jobs/{job_id}/cancel",
    response_model=QueueJobResult,
    summary="Cancel a queued or active download",
)
def cancel_job(job_id: str, queue: QueueDependency) -> QueueJobResult:
    return queue_job_result(queue.cancel(job_id))


@router.post(
    "/queue/jobs/{job_id}/retry",
    response_model=QueueJobResult,
    summary="Retry a failed or interrupted download",
)
def retry_job(job_id: str, queue: QueueDependency) -> QueueJobResult:
    return queue_job_result(queue.retry(job_id))
