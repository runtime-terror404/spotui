from __future__ import annotations

from fastapi import APIRouter

from spotui.api.v1.dependencies import LibraryDependency
from spotui.schemas.library import (
    LibraryOverviewResult,
    LibraryScanQueuedResult,
    library_overview_result,
)

router = APIRouter()


@router.get(
    "/library",
    response_model=LibraryOverviewResult,
    summary="List library roots and scan progress",
)
def read_library(library: LibraryDependency) -> LibraryOverviewResult:
    return library_overview_result(library.overview())


@router.post(
    "/library/scan",
    response_model=LibraryScanQueuedResult,
    status_code=202,
    summary="Request a read-only library rescan",
)
def scan_library(library: LibraryDependency) -> LibraryScanQueuedResult:
    return LibraryScanQueuedResult(queued=library.request_scan())
