from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from spotui.api.v1.dependencies import ImportDependency
from spotui.domain.errors import ImportNotFoundError
from spotui.schemas.imports import (
    CreateImportRequest,
    EnqueueImportRequest,
    ImportEnqueueResponse,
    ImportListResult,
    ImportSessionDetailResult,
    SelectCandidateRequest,
    import_detail_result,
    import_enqueue_result,
    import_session_result,
)
from spotui.services.imports import ImportService

router = APIRouter()

_KEEPALIVE_SECONDS = 15.0


@router.post(
    "/imports",
    response_model=ImportSessionDetailResult,
    status_code=201,
    summary="Extract a public Spotify album or playlist",
)
def create_import(
    body: CreateImportRequest,
    imports: ImportDependency,
) -> ImportSessionDetailResult:
    return import_detail_result(imports.create(body.url))


@router.get(
    "/imports",
    response_model=ImportListResult,
    summary="List active and completed Spotify imports",
)
def list_imports(imports: ImportDependency) -> ImportListResult:
    return ImportListResult(
        imports=[import_session_result(item) for item in imports.list_sessions()]
    )


@router.get(
    "/imports/{session_id}",
    response_model=ImportSessionDetailResult,
    summary="Read an import and its progressive candidates",
)
def get_import(session_id: str, imports: ImportDependency) -> ImportSessionDetailResult:
    return import_detail_result(imports.get(session_id))


@router.post(
    "/imports/{session_id}/pause",
    response_model=ImportSessionDetailResult,
    summary="Pause scheduling new candidate searches",
)
def pause_import(
    session_id: str,
    imports: ImportDependency,
) -> ImportSessionDetailResult:
    return import_detail_result(imports.pause(session_id))


@router.post(
    "/imports/{session_id}/resume",
    response_model=ImportSessionDetailResult,
    summary="Resume candidate searches",
)
def resume_import(
    session_id: str,
    imports: ImportDependency,
) -> ImportSessionDetailResult:
    return import_detail_result(imports.resume(session_id))


@router.post(
    "/imports/{session_id}/cancel",
    status_code=204,
    summary="Cancel an active import and discard unqueued review data",
)
def cancel_import(session_id: str, imports: ImportDependency) -> Response:
    imports.cancel(session_id)
    return Response(status_code=204)


@router.delete(
    "/imports/{session_id}",
    status_code=204,
    summary="Delete a completed import without deleting jobs or media",
)
def delete_import(session_id: str, imports: ImportDependency) -> Response:
    imports.delete(session_id)
    return Response(status_code=204)


@router.post(
    "/imports/{session_id}/sources/{source_id}/select",
    response_model=ImportSessionDetailResult,
    summary="Explicitly select one Amazon candidate for an occurrence",
)
def select_candidate(
    session_id: str,
    source_id: str,
    body: SelectCandidateRequest,
    imports: ImportDependency,
) -> ImportSessionDetailResult:
    return import_detail_result(
        imports.select_candidate(session_id, source_id, body.candidate_id)
    )


@router.post(
    "/imports/{session_id}/sources/{source_id}/skip",
    response_model=ImportSessionDetailResult,
    summary="Skip a source occurrence",
)
def skip_source(
    session_id: str,
    source_id: str,
    imports: ImportDependency,
) -> ImportSessionDetailResult:
    return import_detail_result(imports.skip_source(session_id, source_id))


@router.post(
    "/imports/{session_id}/sources/{source_id}/search",
    response_model=ImportSessionDetailResult,
    summary="Run a fresh Amazon search for one occurrence",
)
def search_source(
    session_id: str,
    source_id: str,
    imports: ImportDependency,
) -> ImportSessionDetailResult:
    return import_detail_result(imports.search_source(session_id, source_id))


@router.post(
    "/imports/{session_id}/enqueue",
    response_model=ImportEnqueueResponse,
    summary="Add explicitly selected occurrences to the download queue",
)
def enqueue_selected(
    session_id: str,
    body: EnqueueImportRequest,
    imports: ImportDependency,
) -> ImportEnqueueResponse:
    return import_enqueue_result(
        imports.enqueue_selected(
            session_id,
            force_library=body.force_library,
        )
    )


async def _event_stream(
    session_id: str,
    request: Request,
    imports: ImportService,
) -> AsyncIterator[str]:
    last_revision: int | None = None
    last_keepalive = time.monotonic()
    while True:
        if await request.is_disconnected():
            break
        revision = await run_in_threadpool(imports.session_revision, session_id)
        if revision is None:
            payload = json.dumps({"import_id": session_id})
            yield f"event: deleted\ndata: {payload}\n\n"
            break
        if last_revision is None or revision != last_revision:
            last_revision = revision
            payload = json.dumps(
                {"import_id": session_id, "revision": revision}
            )
            yield f"id: {revision}\nevent: import\ndata: {payload}\n\n"
            last_keepalive = time.monotonic()
        elif time.monotonic() - last_keepalive >= _KEEPALIVE_SECONDS:
            yield ": keep-alive\n\n"
            last_keepalive = time.monotonic()
        await asyncio.sleep(0.5)


@router.get(
    "/imports/{session_id}/events",
    summary="Stream import revisions for authoritative client refresh",
)
async def import_events(
    session_id: str,
    request: Request,
    imports: ImportDependency,
) -> StreamingResponse:
    revision = await run_in_threadpool(imports.session_revision, session_id)
    if revision is None:
        raise ImportNotFoundError("Import session not found.")
    return StreamingResponse(
        _event_stream(session_id, request, imports),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
