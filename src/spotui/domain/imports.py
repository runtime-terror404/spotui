"""Spotify import sessions, source occurrences, candidates, and review states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from spotui.domain.library import LibraryMatch
from spotui.domain.spotify import SpotifyEntityType


class ImportStatus(StrEnum):
    EXTRACTING = "extracting"
    MATCHING = "matching"
    PAUSED = "paused"
    MATCHING_COMPLETE = "matching_complete"


ACTIVE_IMPORT_STATUSES: frozenset[ImportStatus] = frozenset(
    {
        ImportStatus.EXTRACTING,
        ImportStatus.MATCHING,
        ImportStatus.PAUSED,
    }
)


class MatchingStatus(StrEnum):
    PENDING = "pending"
    SEARCHING = "searching"
    CANDIDATES_READY = "candidates_ready"
    NO_RESULTS = "no_results"
    FAILED = "failed"


TERMINAL_MATCHING_STATUSES: frozenset[MatchingStatus] = frozenset(
    {
        MatchingStatus.CANDIDATES_READY,
        MatchingStatus.NO_RESULTS,
        MatchingStatus.FAILED,
    }
)


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    SELECTED = "selected"
    SKIPPED = "skipped"


class ImportQueueOutcome(StrEnum):
    NONE = "none"
    QUEUED = "queued"
    DUPLICATE = "duplicate"
    SKIPPED_LIBRARY = "skipped_library"


@dataclass(frozen=True, slots=True)
class ImportCounts:
    total: int
    pending: int
    searching: int
    matched: int
    no_results: int
    failed: int
    selected: int
    queued: int
    duplicate: int
    skipped: int
    library_skipped: int
    unresolved: int


@dataclass(frozen=True, slots=True)
class ImportSession:
    id: str
    source_url: str
    kind: SpotifyEntityType | None
    spotify_id: str | None
    title: str
    artwork_url: str | None
    status: ImportStatus
    revision: int
    counts: ImportCounts
    last_error: str | None
    created_at: int
    updated_at: int
    matching_started_at: int | None
    matching_completed_at: int | None


@dataclass(frozen=True, slots=True)
class AmazonCandidate:
    id: str
    source_track_id: str
    track_url: str
    track_key: str
    title: str
    artist: str
    album: str
    duration_seconds: float | None
    artwork_url: str | None
    provider_position: int
    rank: int
    score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class CandidateDraft:
    track_url: str
    track_key: str
    title: str
    artist: str
    album: str
    duration_seconds: float | None
    artwork_url: str | None
    provider_position: int
    rank: int
    score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class ImportSourceTrack:
    id: str
    session_id: str
    position: int
    spotify_track_id: str | None
    source_url: str | None
    title: str
    artist: str
    duration_seconds: float | None
    matching_status: MatchingStatus
    review_status: ReviewStatus
    selected_candidate_id: str | None
    library_match: LibraryMatch | None
    queue_outcome: ImportQueueOutcome
    queued_job_id: str | None
    source_duplicate_of_id: str | None
    queued_duplicate_of_source_id: str | None
    attempt_count: int
    last_error: str | None
    candidates: tuple[AmazonCandidate, ...]


@dataclass(frozen=True, slots=True)
class ImportSessionDetail:
    session: ImportSession
    sources: tuple[ImportSourceTrack, ...]


@dataclass(frozen=True, slots=True)
class ImportEnqueueResult:
    detail: ImportSessionDetail
    queued: int
    duplicate: int
    skipped_library: int
