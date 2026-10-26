from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from spotui.domain.amazon import parse_amazon_track_url
from spotui.domain.imports import (
    CandidateDraft,
    ImportStatus,
    MatchingStatus,
    ReviewStatus,
)
from spotui.domain.spotify import (
    SpotifyCollection,
    SpotifyEntityType,
    SpotifyTrackOccurrence,
)
from spotui.persistence.database import Database
from spotui.persistence.repositories.imports import ImportRepository
from spotui.workers.matching_scheduler import MatchingWorker

PLAYLIST_ID = "1111111111111111111111"


def draft(asin: str = "B000000001") -> CandidateDraft:
    track = parse_amazon_track_url(f"https://music.amazon.com/tracks/{asin}")
    return CandidateDraft(
        track_url=track.original,
        track_key=track.track_key,
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


@dataclass
class SlowMatching:
    delay: float = 0.03
    concurrency: int = 0
    max_concurrency: int = 0
    calls: int = 0
    calls_by_title: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def find_candidates(self, *, title: str, artist: str, duration_seconds=None):
        del artist, duration_seconds
        with self._lock:
            self.calls += 1
            self.calls_by_title.append(title)
            self.concurrency += 1
            self.max_concurrency = max(self.max_concurrency, self.concurrency)
        try:
            time.sleep(self.delay)
            return (draft(),)
        finally:
            with self._lock:
                self.concurrency -= 1


def make_session(repository: ImportRepository, count: int) -> str:
    session = repository.create_extracting_session(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )
    tracks = tuple(
        SpotifyTrackOccurrence(
            position=index,
            spotify_track_id=f"{index:022d}",
            source_url=f"https://open.spotify.com/track/{index:022d}",
            title=f"Song {index}",
            artist="Artist",
            duration_seconds=180.0,
        )
        for index in range(count)
    )
    repository.save_extraction(
        session.id,
        SpotifyCollection(
            kind=SpotifyEntityType.PLAYLIST,
            spotify_id=PLAYLIST_ID,
            title="Road Trip",
            artwork_url=None,
            tracks=tracks,
        ),
    )
    return session.id


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before the timeout")


def test_matching_worker_bounds_concurrency_and_completes(
    migrated_database_url: str,
) -> None:
    database = Database.from_url(migrated_database_url)
    try:
        repository = ImportRepository(database.session_factory)
        matching = SlowMatching()
        worker = MatchingWorker(repository, matching, concurrency=2)
        session_id = make_session(repository, 6)
        worker.start_session(session_id)
        try:
            wait_until(
                lambda: repository.get_session(session_id).status
                is ImportStatus.MATCHING_COMPLETE
            )
        finally:
            worker.close()

        detail = repository.get_session_detail(session_id)
        assert matching.max_concurrency <= 2
        assert matching.max_concurrency >= 1
        assert matching.calls == 6
        assert detail.session.status is ImportStatus.MATCHING_COMPLETE
        assert detail.session.matching_completed_at is not None
        assert all(
            source.matching_status is MatchingStatus.CANDIDATES_READY
            for source in detail.sources
        )
        assert all(
            source.review_status is ReviewStatus.UNREVIEWED
            and source.selected_candidate_id is None
            for source in detail.sources
        )
        assert all(len(source.candidates) == 1 for source in detail.sources)

        second = repository.create_extracting_session(
            f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
        )
        assert second.status is ImportStatus.EXTRACTING
    finally:
        database.dispose()


def test_pause_stops_new_searches_and_resume_finishes(
    migrated_database_url: str,
) -> None:
    database = Database.from_url(migrated_database_url)
    try:
        repository = ImportRepository(database.session_factory)
        matching = SlowMatching(delay=0.02)
        worker = MatchingWorker(repository, matching, concurrency=1)
        session_id = make_session(repository, 12)
        worker.start_session(session_id)
        try:
            wait_until(lambda: matching.calls >= 1)
            repository.pause_session(session_id)
            worker.pause(session_id)
            time.sleep(0.15)
            paused_calls = matching.calls
            time.sleep(0.2)
            assert matching.calls <= paused_calls + 1

            repository.resume_session(session_id)
            worker.resume(session_id)
            wait_until(
                lambda: repository.get_session(session_id).status
                is ImportStatus.MATCHING_COMPLETE
            )
        finally:
            worker.close()

        assert matching.calls == 12
        assert matching.max_concurrency == 1
    finally:
        database.dispose()
