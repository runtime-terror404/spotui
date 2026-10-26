from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spotui.app import create_app
from spotui.domain.errors import (
    ActiveImportConflictError,
    DownloaderUnavailableError,
    ImportNotFoundError,
    ImportStateError,
)
from spotui.domain.imports import (
    AmazonCandidate,
    ImportCounts,
    ImportEnqueueResult,
    ImportQueueOutcome,
    ImportSession,
    ImportSessionDetail,
    ImportSourceTrack,
    ImportStatus,
    MatchingStatus,
    ReviewStatus,
)
from spotui.domain.library import LibraryMatch
from spotui.domain.spotify import (
    SpotifyEntityType,
    SpotifyExtractionError,
    SpotifyTimeoutError,
    SpotifyUrlError,
)
from spotui.runtime import ApplicationRuntime
from spotui.schemas.errors import ErrorCode
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.imports import ImportService
from spotui.services.search import SearchService
from tests.api.helpers import assert_problem
from tests.fakes import FakeCatalog


def make_detail() -> ImportSessionDetail:
    counts = ImportCounts(
        total=1,
        pending=0,
        searching=0,
        matched=1,
        no_results=0,
        failed=0,
        selected=1,
        queued=0,
        duplicate=0,
        skipped=0,
        library_skipped=0,
        unresolved=0,
    )
    session = ImportSession(
        id="session-1",
        source_url="https://open.spotify.com/playlist/1111111111111111111111",
        kind=SpotifyEntityType.PLAYLIST,
        spotify_id="1111111111111111111111",
        title="Road Trip",
        artwork_url="https://images.example/cover.jpg",
        status=ImportStatus.MATCHING,
        revision=4,
        counts=counts,
        last_error=None,
        created_at=1_700_000_000,
        updated_at=1_700_000_100,
        matching_started_at=1_700_000_000,
        matching_completed_at=None,
    )
    candidate = AmazonCandidate(
        id="candidate-1",
        source_track_id="source-1",
        track_url="https://music.amazon.com/tracks/B000000001",
        track_key="amazon:B000000001",
        title="Song",
        artist="Artist",
        album="",
        duration_seconds=None,
        artwork_url=None,
        provider_position=0,
        rank=1,
        score=0.95,
        explanation="Exact title with a matching artist",
    )
    source = ImportSourceTrack(
        id="source-1",
        session_id=session.id,
        position=0,
        spotify_track_id="2222222222222222222221",
        source_url="https://open.spotify.com/track/2222222222222222222221",
        title="Song",
        artist="Artist",
        duration_seconds=180.0,
        matching_status=MatchingStatus.CANDIDATES_READY,
        review_status=ReviewStatus.SELECTED,
        selected_candidate_id=candidate.id,
        library_match=LibraryMatch.LIKELY,
        queue_outcome=ImportQueueOutcome.NONE,
        queued_job_id=None,
        source_duplicate_of_id=None,
        queued_duplicate_of_source_id=None,
        attempt_count=1,
        last_error=None,
        candidates=(candidate,),
    )
    return ImportSessionDetail(session=session, sources=(source,))


@dataclass
class FakeImports:
    detail: ImportSessionDetail
    error: Exception | None = None
    enqueue_error: Exception | None = None
    started: int = 0
    closed: int = 0
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def start(self) -> None:
        self.started += 1

    def close(self) -> None:
        self.closed += 1

    def create(self, url: str) -> ImportSessionDetail:
        self.calls.append(("create", url))
        if self.error is not None:
            raise self.error
        return self.detail

    def list_sessions(self):
        return (self.detail.session,)

    def get(self, session_id: str) -> ImportSessionDetail:
        self.calls.append(("get", session_id))
        if self.error is not None:
            raise self.error
        return self.detail

    def pause(self, session_id: str) -> ImportSessionDetail:
        if self.error is not None:
            raise self.error
        return self.detail

    def resume(self, session_id: str) -> ImportSessionDetail:
        if self.error is not None:
            raise self.error
        return self.detail

    def cancel(self, session_id: str) -> None:
        self.calls.append(("cancel", session_id))
        if self.error is not None:
            raise self.error

    def delete(self, session_id: str) -> None:
        self.calls.append(("delete", session_id))
        if self.error is not None:
            raise self.error

    def select_candidate(self, session_id, source_id, candidate_id):
        self.calls.append(("select", session_id, source_id, candidate_id))
        if self.error is not None:
            raise self.error
        return self.detail

    def skip_source(self, session_id, source_id):
        if self.error is not None:
            raise self.error
        return self.detail

    def search_source(self, session_id, source_id):
        if self.error is not None:
            raise self.error
        return self.detail

    def enqueue_selected(self, session_id, *, force_library=False):
        self.calls.append(("enqueue", session_id, str(force_library)))
        if self.enqueue_error is not None:
            raise self.enqueue_error
        return ImportEnqueueResult(
            detail=self.detail,
            queued=1,
            duplicate=0,
            skipped_library=0,
        )

    def session_revision(self, session_id: str) -> int | None:
        self.calls.append(("revision", session_id))
        return self.detail.session.revision


@pytest.fixture
def imports_context(
    runtime: ApplicationRuntime,
    fake_catalog: FakeCatalog,
) -> Iterator[tuple[TestClient, FakeImports]]:
    fake = FakeImports(make_detail())
    runtime.services = ApplicationServices(
        search=SearchService(fake_catalog),
        entity_details=EntityDetailsService(fake_catalog),
        imports=cast(ImportService, fake),
        resources=(),
    )
    app: FastAPI = create_app(runtime, serve_frontend=False)
    with TestClient(app) as client:
        yield client, fake
    assert fake.started == 1
    assert fake.closed == 1


def test_create_list_and_get_import(imports_context) -> None:
    client, fake = imports_context

    created = client.post(
        "/api/v1/imports",
        json={"url": "https://open.spotify.com/playlist/1111111111111111111111"},
    )
    listing = client.get("/api/v1/imports")
    detail = client.get("/api/v1/imports/session-1")

    assert created.status_code == 201
    body = created.json()
    assert body["id"] == "session-1"
    assert body["spotify_type"] == "playlist"
    assert body["counts"]["matched"] == 1
    assert body["counts"]["selected"] == 1
    source = body["sources"][0]
    assert source["library_match"] == "likely"
    assert source["selected_candidate_id"] == "candidate-1"
    assert source["candidates"][0]["rank"] == 1
    assert source["candidates"][0]["explanation"] == (
        "Exact title with a matching artist"
    )
    assert listing.status_code == 200
    assert listing.json()["imports"][0]["id"] == "session-1"
    assert detail.status_code == 200
    assert detail.json()["sources"][0]["id"] == "source-1"
    assert fake.calls[0] == (
        "create",
        "https://open.spotify.com/playlist/1111111111111111111111",
    )


def test_review_actions_and_enqueue(imports_context) -> None:
    client, fake = imports_context

    selected = client.post(
        "/api/v1/imports/session-1/sources/source-1/select",
        json={"candidate_id": "candidate-1"},
    )
    skipped = client.post(
        "/api/v1/imports/session-1/sources/source-1/skip"
    )
    searched = client.post(
        "/api/v1/imports/session-1/sources/source-1/search"
    )
    enqueued = client.post(
        "/api/v1/imports/session-1/enqueue",
        json={"force_library": True},
    )

    assert selected.status_code == 200
    assert skipped.status_code == 200
    assert searched.status_code == 200
    assert enqueued.status_code == 200
    assert enqueued.json()["queued"] == 1
    assert enqueued.json()["session"]["id"] == "session-1"
    assert ("select", "session-1", "source-1", "candidate-1") in fake.calls
    assert ("enqueue", "session-1", "True") in fake.calls


def test_pause_resume_cancel_and_delete(imports_context) -> None:
    client, fake = imports_context

    assert client.post("/api/v1/imports/session-1/pause").status_code == 200
    assert client.post("/api/v1/imports/session-1/resume").status_code == 200
    cancelled = client.post("/api/v1/imports/session-1/cancel")
    deleted = client.delete("/api/v1/imports/session-1")

    assert cancelled.status_code == 204
    assert deleted.status_code == 204
    assert ("cancel", "session-1") in fake.calls
    assert ("delete", "session-1") in fake.calls


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (SpotifyUrlError("Not a Spotify link."), 400, ErrorCode.INVALID_URL),
        (
            SpotifyExtractionError("Spotify page could not be read."),
            502,
            ErrorCode.SPOTIFY_EXTRACTION_FAILED,
        ),
        (
            SpotifyTimeoutError("Spotify did not respond in time."),
            504,
            ErrorCode.SPOTIFY_EXTRACTION_FAILED,
        ),
        (
            ActiveImportConflictError("Another import is active."),
            409,
            ErrorCode.ACTIVE_IMPORT_CONFLICT,
        ),
    ],
)
def test_create_error_mapping(imports_context, error, status_code, code) -> None:
    client, fake = imports_context
    fake.error = error

    response = client.post(
        "/api/v1/imports",
        json={"url": "https://open.spotify.com/playlist/1111111111111111111111"},
    )

    body = assert_problem(response, status_code, code)
    assert body["detail"] == str(error)


def test_import_not_found_and_state_errors(imports_context) -> None:
    client, fake = imports_context
    fake.error = ImportNotFoundError("Import session not found.")
    assert_problem(
        client.get("/api/v1/imports/missing"),
        404,
        ErrorCode.IMPORT_NOT_FOUND,
    )

    fake.error = ImportStateError("Only a paused import can be resumed.")
    assert_problem(
        client.post("/api/v1/imports/session-1/resume"),
        409,
        ErrorCode.INVALID_TRANSITION,
    )


def test_enqueue_requires_the_downloader(imports_context) -> None:
    client, fake = imports_context
    fake.enqueue_error = DownloaderUnavailableError(
        "The managed lucidadl downloader is not installed."
    )

    response = client.post(
        "/api/v1/imports/session-1/enqueue",
        json={"force_library": False},
    )

    assert_problem(response, 503, ErrorCode.DOWNLOADER_UNAVAILABLE)


def test_import_routes_require_the_service(client) -> None:
    listing = client.get("/api/v1/imports")
    create = client.post(
        "/api/v1/imports",
        json={"url": "https://open.spotify.com/playlist/1111111111111111111111"},
    )

    assert_problem(listing, 503, ErrorCode.IMPORTS_UNAVAILABLE)
    assert_problem(create, 503, ErrorCode.IMPORTS_UNAVAILABLE)


def test_import_event_stream_emits_a_revision(imports_context) -> None:
    client, fake = imports_context

    with client.stream("GET", "/api/v1/imports/session-1/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = response.iter_lines()
        first = next(lines)
        event = next(lines)
        data = next(lines)

    assert first == "id: 4"
    assert event == "event: import"
    assert '"revision": 4' in data
    assert ("revision", "session-1") in fake.calls
