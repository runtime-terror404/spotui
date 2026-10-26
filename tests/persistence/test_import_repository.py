from __future__ import annotations

import pytest
from sqlalchemy import func, select

from spotui.domain.amazon import parse_amazon_track_url
from spotui.domain.errors import ActiveImportConflictError
from spotui.domain.imports import (
    CandidateDraft,
    ImportQueueOutcome,
    ImportStatus,
    MatchingStatus,
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
from spotui.persistence.models import SourceTrack as SourceTrackRow
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.persistence.repositories.imports import ImportRepository

PLAYLIST_ID = "1111111111111111111111"


def collection(*occurrences: SpotifyTrackOccurrence) -> SpotifyCollection:
    return SpotifyCollection(
        kind=SpotifyEntityType.PLAYLIST,
        spotify_id=PLAYLIST_ID,
        title="Road Trip",
        artwork_url="https://images.example/cover.jpg",
        tracks=occurrences,
    )


def occurrence(
    position: int,
    title: str,
    artist: str,
    *,
    spotify_id: str = "2222222222222222222221",
    duration: float = 180.0,
) -> SpotifyTrackOccurrence:
    return SpotifyTrackOccurrence(
        position=position,
        spotify_track_id=spotify_id,
        source_url=f"https://open.spotify.com/track/{spotify_id}",
        title=title,
        artist=artist,
        duration_seconds=duration,
    )


def create_matching_session(
    repository: ImportRepository,
    *occurrences: SpotifyTrackOccurrence,
) -> str:
    session = repository.create_extracting_session(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )
    repository.save_extraction(
        session.id,
        collection(*occurrences) if occurrences else collection(
            occurrence(0, "Song", "Artist")
        ),
    )
    return session.id


def candidate_draft(title: str = "Song", artist: str = "Artist") -> CandidateDraft:
    track = parse_amazon_track_url(
        "https://music.amazon.com/tracks/B000000001"
    )
    return CandidateDraft(
        track_url=track.original,
        track_key=track.track_key,
        title=title,
        artist=artist,
        album="",
        duration_seconds=None,
        artwork_url=None,
        provider_position=0,
        rank=1,
        score=0.95,
        explanation="Exact title with a matching artist",
    )


@pytest.fixture
def database(migrated_database_url: str):
    instance = Database.from_url(migrated_database_url)
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture
def repository(database: Database) -> ImportRepository:
    return ImportRepository(database.session_factory)


def test_extraction_preserves_duplicate_occurrences_and_positions(
    repository: ImportRepository,
) -> None:
    session_id = create_matching_session(
        repository,
        occurrence(0, "First Song", "Artist One"),
        occurrence(
            2,
            "Second Song",
            "Artist Two",
            spotify_id="2222222222222222222222",
        ),
        occurrence(3, "First Song", "Artist One"),
    )

    detail = repository.get_session_detail(session_id)

    assert detail.session.status is ImportStatus.MATCHING
    assert detail.session.counts.total == 3
    assert detail.session.counts.pending == 3
    assert detail.session.counts.unresolved == 3
    assert [source.position for source in detail.sources] == [0, 2, 3]
    assert detail.sources[2].source_duplicate_of_id == detail.sources[0].id
    assert detail.sources[1].source_duplicate_of_id is None


def test_only_one_active_import_and_matching_completion_releases_slot(
    repository: ImportRepository,
) -> None:
    session_id = create_matching_session(repository)
    with pytest.raises(ActiveImportConflictError):
        repository.create_extracting_session(
            f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
        )

    source = repository.get_session_detail(session_id).sources[0]
    repository.start_source_search(session_id, source.id, manual=False)
    repository.save_candidates(session_id, source.id, [])

    assert repository.complete_matching_if_ready(session_id) is True
    completed = repository.get_session(session_id)
    assert completed.status is ImportStatus.MATCHING_COMPLETE
    assert completed.counts.no_results == 1
    assert completed.matching_completed_at is not None

    second = repository.create_extracting_session(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )
    assert second.status is ImportStatus.EXTRACTING


def test_selection_is_never_automatic_and_skip_clears_review(
    repository: ImportRepository,
) -> None:
    session_id = create_matching_session(repository)
    source = repository.get_session_detail(session_id).sources[0]
    repository.start_source_search(session_id, source.id, manual=False)
    repository.save_candidates(session_id, source.id, [candidate_draft()])

    detail = repository.get_session_detail(session_id)
    source = detail.sources[0]
    assert source.matching_status is MatchingStatus.CANDIDATES_READY
    assert source.review_status is ReviewStatus.UNREVIEWED
    assert source.selected_candidate_id is None
    assert len(source.candidates) == 1

    repository.select_candidate(
        session_id,
        source.id,
        source.candidates[0].id,
        library_match=LibraryMatch.EXACT,
    )
    selected = repository.get_session_detail(session_id).sources[0]
    assert selected.review_status is ReviewStatus.SELECTED
    assert selected.selected_candidate_id == source.candidates[0].id
    assert selected.library_match is LibraryMatch.EXACT

    repository.skip_source(session_id, source.id)
    skipped = repository.get_session_detail(session_id).sources[0]
    assert skipped.review_status is ReviewStatus.SKIPPED
    assert skipped.selected_candidate_id is None
    assert skipped.library_match is None


def test_pause_and_resume_keep_the_active_slot(
    repository: ImportRepository,
) -> None:
    session_id = create_matching_session(repository)

    paused = repository.pause_session(session_id)
    assert paused.status is ImportStatus.PAUSED
    assert repository.complete_matching_if_ready(session_id) is False
    with pytest.raises(ActiveImportConflictError):
        repository.create_extracting_session(
            f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
        )

    resumed = repository.resume_session(session_id)
    assert resumed.status is ImportStatus.MATCHING


def test_recovery_requeues_interrupted_searches_and_removes_extractions(
    repository: ImportRepository,
) -> None:
    session_id = create_matching_session(repository)
    source = repository.get_session_detail(session_id).sources[0]
    repository.start_source_search(session_id, source.id, manual=False)

    matching = repository.recover_interrupted_imports()

    assert matching == (session_id,)
    recovered = repository.get_session_detail(session_id).sources[0]
    assert recovered.matching_status is MatchingStatus.PENDING

    repository.delete_session(session_id)
    repository.create_extracting_session(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )
    assert repository.recover_interrupted_imports() == ()


def test_delete_session_removes_import_data_but_preserves_jobs(
    repository: ImportRepository,
    database: Database,
) -> None:
    session_id = create_matching_session(repository)
    source = repository.get_session_detail(session_id).sources[0]
    repository.start_source_search(session_id, source.id, manual=False)
    repository.save_candidates(session_id, source.id, [candidate_draft()])
    assert repository.complete_matching_if_ready(session_id) is True

    job_repository = DownloadJobRepository(database.session_factory)
    job = job_repository.enqueue(
        parse_amazon_track_url("https://music.amazon.com/tracks/B000000001"),
        title="Song",
        artist="Artist",
        source_import_id=session_id,
        source_occurrence_id=source.id,
        source_playlist_title="Road Trip",
    ).job
    repository.record_queue_outcome(
        session_id,
        source.id,
        outcome=ImportQueueOutcome.QUEUED,
        job_id=job.id,
        library_match=None,
    )

    repository.delete_session(
        session_id,
        require_status=ImportStatus.MATCHING_COMPLETE,
    )

    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ImportSessionRow)) == 0
        assert session.scalar(select(func.count()).select_from(SourceTrackRow)) == 0
        persisted_job = session.get(DownloadJobRow, job.id)
        assert persisted_job is not None
        assert persisted_job.source_import_id == session_id
        assert persisted_job.source_occurrence_id == source.id
