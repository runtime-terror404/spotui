"""Typed API contracts for Spotify imports and candidate review."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
from spotui.domain.spotify import SpotifyEntityType


class ImportCountsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class AmazonCandidateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    url: str
    track_key: str
    title: str
    artist: str
    album: str
    duration_seconds: float | None = None
    artwork_url: str | None = None
    provider_position: int
    rank: int
    score: float
    explanation: str


class ImportSourceTrackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    position: int
    spotify_track_id: str | None = None
    source_url: str | None = None
    title: str
    artist: str
    duration_seconds: float | None = None
    matching_status: MatchingStatus
    review_status: ReviewStatus
    selected_candidate_id: str | None = None
    library_match: LibraryMatch | None = None
    queue_outcome: ImportQueueOutcome
    queued_job_id: str | None = None
    source_duplicate_of_id: str | None = None
    queued_duplicate_of_source_id: str | None = None
    attempt_count: int
    last_error: str | None = None
    candidates: list[AmazonCandidateResult]


class ImportSessionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_url: str
    spotify_type: SpotifyEntityType | None = None
    spotify_id: str | None = None
    title: str
    artwork_url: str | None = None
    status: ImportStatus
    revision: int
    counts: ImportCountsResult
    last_error: str | None = None
    created_at: int
    updated_at: int
    matching_started_at: int | None = None
    matching_completed_at: int | None = None


class ImportSessionDetailResult(ImportSessionResult):
    sources: list[ImportSourceTrackResult]


class ImportListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imports: list[ImportSessionResult]


class CreateImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)


class EnqueueImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_library: bool = False


class SelectCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=64)


class ImportEnqueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: ImportSessionDetailResult
    queued: int
    duplicate: int
    skipped_library: int


def _counts_result(counts: ImportCounts) -> ImportCountsResult:
    return ImportCountsResult(
        total=counts.total,
        pending=counts.pending,
        searching=counts.searching,
        matched=counts.matched,
        no_results=counts.no_results,
        failed=counts.failed,
        selected=counts.selected,
        queued=counts.queued,
        duplicate=counts.duplicate,
        skipped=counts.skipped,
        library_skipped=counts.library_skipped,
        unresolved=counts.unresolved,
    )


def _session_fields(session: ImportSession) -> dict[str, object]:
    return {
        "id": session.id,
        "source_url": session.source_url,
        "spotify_type": session.kind,
        "spotify_id": session.spotify_id,
        "title": session.title,
        "artwork_url": session.artwork_url,
        "status": session.status,
        "revision": session.revision,
        "counts": _counts_result(session.counts),
        "last_error": session.last_error,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "matching_started_at": session.matching_started_at,
        "matching_completed_at": session.matching_completed_at,
    }


def import_session_result(session: ImportSession) -> ImportSessionResult:
    return ImportSessionResult(**_session_fields(session))


def candidate_result(candidate: AmazonCandidate) -> AmazonCandidateResult:
    return AmazonCandidateResult(
        id=candidate.id,
        url=candidate.track_url,
        track_key=candidate.track_key,
        title=candidate.title,
        artist=candidate.artist,
        album=candidate.album,
        duration_seconds=candidate.duration_seconds,
        artwork_url=candidate.artwork_url,
        provider_position=candidate.provider_position,
        rank=candidate.rank,
        score=candidate.score,
        explanation=candidate.explanation,
    )


def source_track_result(source: ImportSourceTrack) -> ImportSourceTrackResult:
    return ImportSourceTrackResult(
        id=source.id,
        position=source.position,
        spotify_track_id=source.spotify_track_id,
        source_url=source.source_url,
        title=source.title,
        artist=source.artist,
        duration_seconds=source.duration_seconds,
        matching_status=source.matching_status,
        review_status=source.review_status,
        selected_candidate_id=source.selected_candidate_id,
        library_match=source.library_match,
        queue_outcome=source.queue_outcome,
        queued_job_id=source.queued_job_id,
        source_duplicate_of_id=source.source_duplicate_of_id,
        queued_duplicate_of_source_id=source.queued_duplicate_of_source_id,
        attempt_count=source.attempt_count,
        last_error=source.last_error,
        candidates=[candidate_result(item) for item in source.candidates],
    )


def import_detail_result(detail: ImportSessionDetail) -> ImportSessionDetailResult:
    return ImportSessionDetailResult(
        **_session_fields(detail.session),
        sources=[source_track_result(source) for source in detail.sources],
    )


def import_enqueue_result(result: ImportEnqueueResult) -> ImportEnqueueResponse:
    return ImportEnqueueResponse(
        session=import_detail_result(result.detail),
        queued=result.queued,
        duplicate=result.duplicate,
        skipped_library=result.skipped_library,
    )
