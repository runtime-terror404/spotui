"""Typed API contracts for the library index."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from spotui.domain.library import (
    LibraryOverview,
    LibraryRoot,
    LibraryScan,
    LibraryScanStatus,
)


class LibraryRootResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    path: str
    available: bool
    index_complete: bool
    last_checked_at: int | None = None
    last_scan_at: int | None = None
    file_count: int
    last_error: str | None = None


class LibraryScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    root_id: int
    status: LibraryScanStatus
    started_at: int
    finished_at: int | None = None
    files_seen: int
    files_indexed: int
    files_removed: int
    files_failed: int
    error: str | None = None


class LibraryOverviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roots: list[LibraryRootResult]
    active_scan: LibraryScanResult | None = None
    total_files: int
    unavailable_roots: int


class LibraryScanQueuedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queued: bool


def library_root_result(root: LibraryRoot) -> LibraryRootResult:
    return LibraryRootResult(
        id=root.id,
        path=root.path,
        available=root.available,
        index_complete=root.index_complete,
        last_checked_at=root.last_checked_at,
        last_scan_at=root.last_scan_at,
        file_count=root.file_count,
        last_error=root.last_error,
    )


def library_scan_result(scan: LibraryScan) -> LibraryScanResult:
    return LibraryScanResult(
        id=scan.id,
        root_id=scan.root_id,
        status=scan.status,
        started_at=scan.started_at,
        finished_at=scan.finished_at,
        files_seen=scan.files_seen,
        files_indexed=scan.files_indexed,
        files_removed=scan.files_removed,
        files_failed=scan.files_failed,
        error=scan.error,
    )


def library_overview_result(overview: LibraryOverview) -> LibraryOverviewResult:
    return LibraryOverviewResult(
        roots=[library_root_result(root) for root in overview.roots],
        active_scan=(
            library_scan_result(overview.active_scan)
            if overview.active_scan is not None
            else None
        ),
        total_files=overview.total_files,
        unavailable_roots=overview.unavailable_roots,
    )
