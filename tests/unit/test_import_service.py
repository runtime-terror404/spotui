from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select

from spotui.domain.amazon import parse_amazon_track_url
from spotui.domain.errors import CatalogTimeoutError
from spotui.domain.imports import (
    CandidateDraft,
    ImportQueueOutcome,
    ImportStatus,
    ReviewStatus,
)
from spotui.domain.library import LibraryMatch
from spotui.domain.spotify import (
    SpotifyCollection,
    SpotifyEntityType,
    SpotifyTrackOccurrence,
)
from spotui.persistence.database import Database
from spotui.persistence.models import DownloadJob as DownloadJobRow
from spotui.persistence.models import ImportSession as ImportSessionRow
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.persistence.repositories.imports import ImportRepository
from spotui.services.imports import ImportService
from spotui.services.queue import QueueService
from tests.fakes import FakeDownloader, FakeLibrary, FakeWorker

PLAYLIST_ID = "1111111111111111111111"


def collection(*tracks: SpotifyTrackOccurrence) -> SpotifyCollection:
    return SpotifyCollection(
        kind=SpotifyEntityType.PLAYLIST,
        spotify_id=PLAYLIST_ID,
        title="Road Trip",
        artwork_url=None,
        tracks=tracks,
    )


def occurrence(
    position: int = 0,
    *,
    spotify_id: str = "2222222222222222222221",
    title: str = "Song",
    artist: str = "Artist",
) -> SpotifyTrackOccurrence:
    return SpotifyTrackOccurrence(
        position=position,
        spotify_track_id=spotify_id,
        source_url=f"https://open.spotify.com/track/{spotify_id}",
        title=title,
        artist=artist,
        duration_seconds=180.0,
    )


@dataclass
class FakeSpotify:
    result: SpotifyCollection
    error: Exception | None = None
    calls: list[str] = field(default_factory=list)

    def extract(self, url: str) -> SpotifyCollection:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class FakeMatchingWorker:
    started: int = 0
    closed: int = 0
    started_sessions: list[str] = field(default_factory=list)
    paused: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.started += 1

    def close(self) -> None:
        self.closed += 1

    def start_session(self, session_id: str) -> None:
        self.started_sessions.append(session_id)

    def pause(self, session_id: str) -> None:
        self.paused.append(session_id)

    def resume(self, session_id: str) -> None:
        self.resumed.append(session_id)

    def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)


@dataclass
class FakeMatching:
    drafts: tuple[CandidateDraft, ...]
    error: Exception | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def find_candidates(self, *, title: str, artist: str, duration_seconds=None):
        del duration_seconds
        self.calls.append((title, artist))
        if self.error is not None:
            raise self.error
        return self.drafts


def candidate(asin: str = "B000000001", title: str = "Song") -> CandidateDraft:
    track = parse_amazon_track_url(f"https://music.amazon.com/tracks/{asin}")
    return CandidateDraft(
        track_url=track.original,
        track_key=track.track_key,
        title=title,
        artist="Artist",
        album="",
        duration_seconds=None,
        artwork_url=None,
        provider_position=0,
        rank=1,
        score=0.95,
        explanation="Exact title with a matching artist",
    )


@dataclass
class ImportContext:
    database: Database
    repository: ImportRepository
    job_repository: DownloadJobRepository
    queue_worker: FakeWorker
    spotify: FakeSpotify
    matching: FakeMatching
    matching_worker: FakeMatchingWorker
    library: FakeLibrary
    service: ImportService


@pytest.fixture
def context(migrated_database_url: str) -> ImportContext:
    database = Database.from_url(migrated_database_url)
    repository = ImportRepository(database.session_factory)
    job_repository = DownloadJobRepository(database.session_factory)
    queue_worker = FakeWorker()
    library = FakeLibrary()
    queue = QueueService(
        job_repository,
        queue_worker,
        FakeDownloader(),
        library=library,
    )
    spotify = FakeSpotify(collection(occurrence()))
    matching = FakeMatching((candidate(),))
    matching_worker = FakeMatchingWorker()
    service = ImportService(
        repository,
        spotify,
        matching,
        matching_worker,
        queue,
        library=library,
    )
    try:
        yield ImportContext(
            database=database,
            repository=repository,
            job_repository=job_repository,
            queue_worker=queue_worker,
            spotify=spotify,
            matching=matching,
            matching_worker=matching_worker,
            library=library,
            service=service,
        )
    finally:
        database.dispose()


def create(context: ImportContext, *tracks: SpotifyTrackOccurrence):
    context.spotify.result = collection(*(tracks or (occurrence(),)))
    return context.service.create(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )


def make_candidates_ready(
    context: ImportContext,
    session_id: str,
    source_id: str,
    *,
    title: str = "Song",
):
    context.matching.drafts = (candidate(title=title),)
    return context.service.search_source(session_id, source_id)


def test_create_extracts_and_starts_matching(context: ImportContext) -> None:
    detail = create(context)

    assert detail.session.status is ImportStatus.MATCHING
    assert len(detail.sources) == 1
    assert context.spotify.calls == [
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    ]
    assert context.matching_worker.started_sessions == [detail.session.id]


def test_extraction_failure_releases_the_active_slot(
    context: ImportContext,
) -> None:
    from spotui.domain.spotify import SpotifyExtractionError

    context.spotify.error = SpotifyExtractionError("Spotify is private.")
    with pytest.raises(SpotifyExtractionError):
        context.service.create(
            f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
        )
    assert context.repository.list_sessions() == ()

    context.spotify.error = None
    detail = context.service.create(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )
    assert detail.session.status is ImportStatus.MATCHING


def test_selection_and_enqueue_are_explicit_and_idempotent(
    context: ImportContext,
) -> None:
    detail = create(context)
    source = detail.sources[0]
    make_candidates_ready(context, detail.session.id, source.id)

    before = context.repository.get_session_detail(detail.session.id).sources[0]
    assert before.review_status is ReviewStatus.UNREVIEWED
    assert before.selected_candidate_id is None

    selected = context.service.select_candidate(
        detail.session.id,
        source.id,
        before.candidates[0].id,
    ).sources[0]
    assert selected.review_status is ReviewStatus.SELECTED

    first = context.service.enqueue_selected(detail.session.id)
    second = context.service.enqueue_selected(detail.session.id)

    assert first.queued == 1
    assert second.queued == 0
    queued_source = first.detail.sources[0]
    assert queued_source.queue_outcome is ImportQueueOutcome.QUEUED
    assert queued_source.queued_job_id is not None
    assert first.detail.session.counts.queued == 1
    assert first.detail.session.counts.selected == 1
    jobs = context.job_repository.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].source_import_id == detail.session.id
    assert jobs[0].source_occurrence_id == source.id


def test_enqueue_recovers_an_existing_job_owned_by_the_same_occurrence(
    context: ImportContext,
) -> None:
    detail = create(context)
    source = detail.sources[0]
    make_candidates_ready(context, detail.session.id, source.id)
    source = context.repository.get_session_detail(detail.session.id).sources[0]
    context.service.select_candidate(detail.session.id, source.id, source.candidates[0].id)
    first = context.service.enqueue_selected(detail.session.id)
    first_job_id = first.detail.sources[0].queued_job_id
    assert first_job_id is not None

    context.repository.record_queue_outcome(
        detail.session.id,
        source.id,
        outcome=ImportQueueOutcome.NONE,
        job_id=None,
        library_match=None,
    )
    recovered = context.service.enqueue_selected(detail.session.id)

    assert recovered.queued == 1
    assert recovered.duplicate == 0
    assert recovered.detail.sources[0].queued_job_id == first_job_id
    assert len(context.job_repository.list_jobs()) == 1


def test_duplicate_source_occurrences_keep_separate_rows_and_flag_duplicate(
    context: ImportContext,
) -> None:
    detail = create(
        context,
        occurrence(0),
        occurrence(1),
    )
    context.matching.drafts = (candidate(),)
    for source in context.repository.get_session_detail(detail.session.id).sources:
        updated = context.service.search_source(detail.session.id, source.id)
        selected_source = next(
            item for item in updated.sources if item.id == source.id
        )
        context.service.select_candidate(
            detail.session.id,
            source.id,
            selected_source.candidates[0].id,
        )

    result = context.service.enqueue_selected(detail.session.id)

    assert result.queued == 1
    assert result.duplicate == 1
    assert len(result.detail.sources) == 2
    assert result.detail.sources[1].queue_outcome is ImportQueueOutcome.DUPLICATE
    assert result.detail.sources[1].queued_duplicate_of_source_id == (
        result.detail.sources[0].id
    )
    assert result.detail.session.counts.duplicate == 1


def test_selected_track_can_be_queued_before_matching_completes(
    context: ImportContext,
) -> None:
    detail = create(context, occurrence(0), occurrence(1, spotify_id="2222222222222222222222"))
    first = detail.sources[0]
    make_candidates_ready(context, detail.session.id, first.id)
    updated = context.service.select_candidate(
        detail.session.id,
        first.id,
        context.repository.get_session_detail(detail.session.id).sources[0].candidates[0].id,
    )
    result = context.service.enqueue_selected(detail.session.id)

    remaining = [source for source in updated.sources if source.id != first.id][0]
    assert remaining.matching_status.value == "pending"
    assert result.queued == 1
    assert result.detail.session.status is ImportStatus.MATCHING


def test_library_matches_are_skipped_without_force_and_can_be_overridden(
    context: ImportContext,
) -> None:
    context.library.in_library = True
    detail = create(context)
    source = detail.sources[0]
    make_candidates_ready(context, detail.session.id, source.id)
    candidate_id = context.repository.get_session_detail(
        detail.session.id
    ).sources[0].candidates[0].id
    selection = context.service.select_candidate(
        detail.session.id,
        source.id,
        candidate_id,
    ).sources[0]
    assert selection.library_match is LibraryMatch.LIKELY

    skipped = context.service.enqueue_selected(detail.session.id)
    assert skipped.skipped_library == 1
    assert skipped.detail.sources[0].queue_outcome is ImportQueueOutcome.SKIPPED_LIBRARY
    assert skipped.detail.sources[0].queued_job_id is None
    assert context.job_repository.list_jobs() == ()

    queued = context.service.enqueue_selected(
        detail.session.id,
        force_library=True,
    )
    assert queued.queued == 1
    assert queued.detail.sources[0].queue_outcome is ImportQueueOutcome.QUEUED


def test_pause_resume_and_cancel_delegate_and_preserve_queued_jobs(
    context: ImportContext,
) -> None:
    detail = create(context)
    session_id = detail.session.id
    source = detail.sources[0]
    make_candidates_ready(context, session_id, source.id)
    source = context.repository.get_session_detail(session_id).sources[0]
    context.service.select_candidate(session_id, source.id, source.candidates[0].id)
    context.service.enqueue_selected(session_id)

    paused = context.service.pause(session_id)
    assert paused.session.status is ImportStatus.PAUSED
    assert context.matching_worker.paused == [session_id]
    resumed = context.service.resume(session_id)
    assert resumed.session.status is ImportStatus.MATCHING
    assert context.matching_worker.resumed == [session_id]

    context.service.cancel(session_id)

    assert context.matching_worker.cancelled == [session_id]
    with context.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ImportSessionRow)) == 0
        assert session.scalar(select(func.count()).select_from(DownloadJobRow)) == 1


def test_manual_search_failure_marks_the_source_failed(context: ImportContext) -> None:
    detail = create(context)
    source = detail.sources[0]
    context.matching.error = CatalogTimeoutError("Amazon timed out.")

    with pytest.raises(CatalogTimeoutError):
        context.service.search_source(detail.session.id, source.id)

    failed = context.repository.get_session_detail(detail.session.id).sources[0]
    assert failed.matching_status.value == "failed"
    assert failed.last_error == "Amazon timed out."
