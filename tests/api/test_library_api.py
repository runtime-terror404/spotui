from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi import FastAPI

from spotui.app import create_app
from spotui.domain.library import (
    LibraryOverview,
    LibraryRoot,
    LibraryScan,
    LibraryScanStatus,
)
from spotui.runtime import ApplicationRuntime
from spotui.schemas.errors import ErrorCode
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.library import LibraryService
from spotui.services.search import SearchService
from tests.api.helpers import CSRFTestClient as TestClient
from tests.api.helpers import assert_problem
from tests.fakes import FakeCatalog


@dataclass
class FakeLibraryService:
    overview_result: LibraryOverview
    queued: bool = True
    scan_requests: int = 0
    started: int = 0
    closed: int = 0

    def start(self) -> None:
        self.started += 1

    def close(self) -> None:
        self.closed += 1

    def overview(self) -> LibraryOverview:
        return self.overview_result

    def request_scan(self) -> bool:
        self.scan_requests += 1
        return self.queued


@pytest.fixture
def library_overview() -> LibraryOverview:
    return LibraryOverview(
        roots=(
            LibraryRoot(
                id=1,
                path="/music/main",
                available=True,
                index_complete=True,
                last_checked_at=1_700_000_100,
                last_scan_at=1_700_000_100,
                file_count=42,
                last_error=None,
            ),
            LibraryRoot(
                id=2,
                path="/music/archive",
                available=False,
                index_complete=False,
                last_checked_at=1_700_000_200,
                last_scan_at=None,
                file_count=10,
                last_error="Library root is unavailable.",
            ),
        ),
        active_scan=LibraryScan(
            id=7,
            root_id=1,
            status=LibraryScanStatus.RUNNING,
            started_at=1_700_000_300,
            finished_at=None,
            files_seen=12,
            files_indexed=3,
            files_removed=0,
            files_failed=0,
            error=None,
        ),
    )


@pytest.fixture
def library_context(
    env,
    runtime: ApplicationRuntime,
    migrated_database_url: str,
    fake_catalog: FakeCatalog,
    library_overview: LibraryOverview,
) -> Iterator[tuple[TestClient, FakeLibraryService]]:
    library = FakeLibraryService(library_overview)
    runtime.services = ApplicationServices(
        search=SearchService(fake_catalog),
        entity_details=EntityDetailsService(fake_catalog),
        library=cast(LibraryService, library),
        resources=(),
    )
    app: FastAPI = create_app(runtime, serve_frontend=False)
    with TestClient(app) as client:
        yield client, library
    assert library.started == 1
    assert library.closed == 1


def test_library_overview_reports_roots_availability_and_progress(
    library_context: tuple[TestClient, FakeLibraryService],
) -> None:
    client, _library = library_context

    response = client.get("/api/v1/library")

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 52
    assert body["unavailable_roots"] == 1
    assert body["roots"][0] == {
        "id": 1,
        "path": "/music/main",
        "available": True,
        "index_complete": True,
        "last_checked_at": 1_700_000_100,
        "last_scan_at": 1_700_000_100,
        "file_count": 42,
        "last_error": None,
    }
    assert body["roots"][1]["available"] is False
    assert body["roots"][1]["index_complete"] is False
    assert body["roots"][1]["last_error"] == "Library root is unavailable."
    assert body["active_scan"]["status"] == "running"
    assert body["active_scan"]["files_seen"] == 12
    assert body["active_scan"]["files_indexed"] == 3


def test_rescan_queues_and_returns_accepted(
    library_context: tuple[TestClient, FakeLibraryService],
) -> None:
    client, library = library_context

    response = client.post("/api/v1/library/scan")

    assert response.status_code == 202
    assert response.json() == {"queued": True}
    assert library.scan_requests == 1


def test_rescan_without_roots_is_not_queued(
    library_context: tuple[TestClient, FakeLibraryService],
) -> None:
    client, library = library_context
    library.queued = False

    response = client.post("/api/v1/library/scan")

    assert response.status_code == 202
    assert response.json() == {"queued": False}


def test_library_routes_require_the_service(client) -> None:
    overview = client.get("/api/v1/library")
    scan = client.post("/api/v1/library/scan")

    assert_problem(overview, 503, ErrorCode.LIBRARY_UNAVAILABLE)
    assert_problem(scan, 503, ErrorCode.LIBRARY_UNAVAILABLE)
