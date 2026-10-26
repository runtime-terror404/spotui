"""Transactional persistence for Spotify imports, sources, and candidates."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from spotui.domain.errors import (
    ActiveImportConflictError,
    ImportNotFoundError,
    ImportStateError,
    InvalidSelectionError,
)
from spotui.domain.imports import (
    TERMINAL_MATCHING_STATUSES,
    AmazonCandidate,
    CandidateDraft,
    ImportCounts,
    ImportQueueOutcome,
    ImportSession,
    ImportSessionDetail,
    ImportSourceTrack,
    ImportStatus,
    MatchingStatus,
    ReviewStatus,
)
from spotui.domain.library import LibraryMatch, normalize_library_text
from spotui.domain.spotify import SpotifyCollection, SpotifyEntityType
from spotui.persistence.models import AmazonCandidate as AmazonCandidateRow
from spotui.persistence.models import ImportSession as ImportSessionRow
from spotui.persistence.models import SourceTrack as SourceTrackRow

_TERMINAL_VALUES = frozenset(status.value for status in TERMINAL_MATCHING_STATUSES)


def _epoch() -> int:
    return int(time.time())


def _bump(session: ImportSessionRow, now: int) -> None:
    session.revision += 1
    session.updated_at = now


def _to_candidate(row: AmazonCandidateRow) -> AmazonCandidate:
    return AmazonCandidate(
        id=row.id,
        source_track_id=row.source_track_id,
        track_url=row.track_url,
        track_key=row.track_key,
        title=row.title,
        artist=row.artist,
        album=row.album,
        duration_seconds=row.duration_seconds,
        artwork_url=row.artwork_url,
        provider_position=row.provider_position,
        rank=row.rank,
        score=row.score,
        explanation=row.explanation,
    )


def _to_source(row: SourceTrackRow) -> ImportSourceTrack:
    return ImportSourceTrack(
        id=row.id,
        session_id=row.session_id,
        position=row.position,
        spotify_track_id=row.spotify_track_id,
        source_url=row.source_url,
        title=row.title,
        artist=row.artist,
        duration_seconds=row.duration_seconds,
        matching_status=MatchingStatus(row.matching_status),
        review_status=ReviewStatus(row.review_status),
        selected_candidate_id=row.selected_candidate_id,
        library_match=LibraryMatch(row.library_match) if row.library_match else None,
        queue_outcome=ImportQueueOutcome(row.queue_outcome),
        queued_job_id=row.queued_job_id,
        source_duplicate_of_id=row.source_duplicate_of_id,
        queued_duplicate_of_source_id=row.queued_duplicate_of_source_id,
        attempt_count=row.attempt_count,
        last_error=row.last_error,
        candidates=tuple(_to_candidate(candidate) for candidate in row.candidates),
    )


def _to_session(row: ImportSessionRow, counts: ImportCounts) -> ImportSession:
    return ImportSession(
        id=row.id,
        source_url=row.source_url,
        kind=SpotifyEntityType(row.spotify_type) if row.spotify_type else None,
        spotify_id=row.spotify_id,
        title=row.title,
        artwork_url=row.artwork_url,
        status=ImportStatus(row.status),
        revision=row.revision,
        counts=counts,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
        matching_started_at=row.matching_started_at,
        matching_completed_at=row.matching_completed_at,
    )


def _counts_from_rows(rows: Sequence[SourceTrackRow]) -> ImportCounts:
    matching = {status: 0 for status in MatchingStatus}
    review = {status: 0 for status in ReviewStatus}
    queue = {outcome: 0 for outcome in ImportQueueOutcome}
    for row in rows:
        matching[MatchingStatus(row.matching_status)] += 1
        review[ReviewStatus(row.review_status)] += 1
        queue[ImportQueueOutcome(row.queue_outcome)] += 1
    return ImportCounts(
        total=len(rows),
        pending=matching[MatchingStatus.PENDING],
        searching=matching[MatchingStatus.SEARCHING],
        matched=matching[MatchingStatus.CANDIDATES_READY],
        no_results=matching[MatchingStatus.NO_RESULTS],
        failed=matching[MatchingStatus.FAILED],
        selected=review[ReviewStatus.SELECTED],
        queued=queue[ImportQueueOutcome.QUEUED],
        duplicate=queue[ImportQueueOutcome.DUPLICATE],
        skipped=review[ReviewStatus.SKIPPED],
        library_skipped=queue[ImportQueueOutcome.SKIPPED_LIBRARY],
        unresolved=review[ReviewStatus.UNREVIEWED],
    )


class ImportRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], int] = _epoch,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._write_lock = threading.Lock()

    @contextmanager
    def _write(self) -> Iterator[Session]:
        """Serialize short SQLite read-then-write transactions across matcher tasks."""
        with self._write_lock:
            with self._session_factory.begin() as session:
                yield session

    def create_extracting_session(self, source_url: str) -> ImportSession:
        now = self._clock()
        session_id = uuid.uuid4().hex
        try:
            with self._write() as session:
                row = ImportSessionRow(
                    id=session_id,
                    source_url=source_url,
                    spotify_type=None,
                    spotify_id=None,
                    title="",
                    artwork_url=None,
                    status=ImportStatus.EXTRACTING.value,
                    active_slot=1,
                    revision=0,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                    matching_started_at=None,
                    matching_completed_at=None,
                )
                session.add(row)
                session.flush()
                return _to_session(row, _counts_from_rows([]))
        except IntegrityError as exc:
            raise ActiveImportConflictError(
                "Another Spotify import is already active. Pause, cancel, or finish it first."
            ) from exc

    def save_extraction(self, session_id: str, collection: SpotifyCollection) -> None:
        now = self._clock()
        with self._write() as session:
            row = session.get(ImportSessionRow, session_id)
            if row is None:
                raise ImportNotFoundError("Import session not found.")
            if row.status != ImportStatus.EXTRACTING.value:
                raise ImportStateError("This import is no longer extracting.")
            if not collection.tracks:
                raise ImportStateError("The Spotify item did not contain any tracks.")
            first_occurrences: dict[object, str] = {}
            for track in collection.tracks:
                source_id = uuid.uuid4().hex
                identity: object
                if track.spotify_track_id:
                    identity = ("spotify", track.spotify_track_id)
                else:
                    identity = (
                        "metadata",
                        normalize_library_text(track.title),
                        normalize_library_text(track.artist),
                    )
                source_duplicate_of_id = first_occurrences.get(identity)
                first_occurrences.setdefault(identity, source_id)
                session.add(
                    SourceTrackRow(
                        id=source_id,
                        session_id=session_id,
                        position=track.position,
                        spotify_track_id=track.spotify_track_id,
                        source_url=track.source_url,
                        title=track.title,
                        artist=track.artist,
                        duration_seconds=track.duration_seconds,
                        matching_status=MatchingStatus.PENDING.value,
                        review_status=ReviewStatus.UNREVIEWED.value,
                        selected_candidate_id=None,
                        library_match=None,
                        queue_outcome=ImportQueueOutcome.NONE.value,
                        queued_job_id=None,
                        source_duplicate_of_id=source_duplicate_of_id,
                        queued_duplicate_of_source_id=None,
                        attempt_count=0,
                        last_error=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            row.spotify_type = collection.kind.value
            row.spotify_id = collection.spotify_id
            row.title = collection.title
            row.artwork_url = collection.artwork_url
            row.status = ImportStatus.MATCHING.value
            row.matching_started_at = now
            row.last_error = None
            _bump(row, now)

    def get_session(self, session_id: str) -> ImportSession:
        with self._session_factory() as session:
            row = session.get(ImportSessionRow, session_id)
            if row is None:
                raise ImportNotFoundError("Import session not found.")
            rows = session.scalars(
                select(SourceTrackRow).where(SourceTrackRow.session_id == session_id)
            ).all()
            return _to_session(row, _counts_from_rows(rows))

    def get_session_detail(self, session_id: str) -> ImportSessionDetail:
        with self._session_factory() as session:
            row = session.get(ImportSessionRow, session_id)
            if row is None:
                raise ImportNotFoundError("Import session not found.")
            sources = session.scalars(
                select(SourceTrackRow)
                .where(SourceTrackRow.session_id == session_id)
                .options(selectinload(SourceTrackRow.candidates))
                .order_by(SourceTrackRow.position)
            ).all()
            counts = _counts_from_rows(sources)
            return ImportSessionDetail(
                session=_to_session(row, counts),
                sources=tuple(_to_source(source) for source in sources),
            )

    def list_sessions(self, *, limit: int = 100) -> tuple[ImportSession, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ImportSessionRow)
                .order_by(ImportSessionRow.created_at.desc(), ImportSessionRow.id.desc())
                .limit(limit)
            ).all()
            sessions = []
            for row in rows:
                sources = session.scalars(
                    select(SourceTrackRow).where(SourceTrackRow.session_id == row.id)
                ).all()
                sessions.append(_to_session(row, _counts_from_rows(sources)))
            return tuple(sessions)

    def session_revision(self, session_id: str) -> int | None:
        with self._session_factory() as session:
            return session.scalar(
                select(ImportSessionRow.revision).where(ImportSessionRow.id == session_id)
            )

    def delete_session(
        self,
        session_id: str,
        *,
        require_status: ImportStatus | None = None,
    ) -> None:
        with self._write() as session:
            row = session.get(ImportSessionRow, session_id)
            if row is None:
                raise ImportNotFoundError("Import session not found.")
            if require_status is not None and row.status != require_status.value:
                raise ImportStateError("This import cannot be deleted in its current state.")
            session.delete(row)

    def recover_interrupted_imports(self) -> tuple[str, ...]:
        now = self._clock()
        with self._write() as session:
            extracting = session.scalars(
                select(ImportSessionRow).where(
                    ImportSessionRow.status == ImportStatus.EXTRACTING.value
                )
            ).all()
            for row in extracting:
                session.delete(row)
            affected = session.scalars(
                select(ImportSessionRow)
                .where(
                    ImportSessionRow.id.in_(
                        select(SourceTrackRow.session_id).where(
                            SourceTrackRow.matching_status == MatchingStatus.SEARCHING.value
                        )
                    )
                )
            ).all()
            for row in affected:
                sources = session.scalars(
                    select(SourceTrackRow).where(
                        SourceTrackRow.session_id == row.id,
                        SourceTrackRow.matching_status == MatchingStatus.SEARCHING.value,
                    )
                ).all()
                if row.status in (
                    ImportStatus.MATCHING.value,
                    ImportStatus.PAUSED.value,
                ):
                    for source in sources:
                        source.matching_status = MatchingStatus.PENDING.value
                        source.updated_at = now
                elif row.status == ImportStatus.MATCHING_COMPLETE.value:
                    for source in sources:
                        source.matching_status = MatchingStatus.FAILED.value
                        source.last_error = "Search interrupted by application restart."
                        source.updated_at = now
                _bump(row, now)
            matching = session.scalars(
                select(ImportSessionRow.id).where(
                    ImportSessionRow.status == ImportStatus.MATCHING.value
                )
            ).all()
            return tuple(matching)

    def pending_source_ids(self, session_id: str, *, limit: int) -> tuple[str, ...]:
        with self._session_factory() as session:
            return tuple(
                session.scalars(
                    select(SourceTrackRow.id)
                    .where(
                        SourceTrackRow.session_id == session_id,
                        SourceTrackRow.matching_status == MatchingStatus.PENDING.value,
                    )
                    .order_by(SourceTrackRow.position.asc())
                    .limit(limit)
                ).all()
            )

    def session_is_matching(self, session_id: str) -> bool:
        with self._session_factory() as session:
            return bool(
                session.scalar(
                    select(ImportSessionRow.id).where(
                        ImportSessionRow.id == session_id,
                        ImportSessionRow.status == ImportStatus.MATCHING.value,
                    )
                )
            )

    def source_search_data(
        self,
        session_id: str,
        source_id: str,
    ) -> tuple[str, str, float | None]:
        with self._session_factory() as session:
            row = self._require_source(session, session_id, source_id)
            return row.title, row.artist, row.duration_seconds

    def start_source_search(
        self,
        session_id: str,
        source_id: str,
        *,
        manual: bool,
    ) -> None:
        now = self._clock()
        with self._write() as session:
            import_row = self._require_session(session, session_id)
            source = self._require_source(session, session_id, source_id)
            if import_row.status == ImportStatus.EXTRACTING.value:
                raise ImportStateError("This import is still extracting.")
            if source.queue_outcome in (
                ImportQueueOutcome.QUEUED.value,
                ImportQueueOutcome.DUPLICATE.value,
            ):
                raise ImportStateError("This occurrence has already been added to the queue.")
            if source.matching_status == MatchingStatus.SEARCHING.value:
                raise ImportStateError("A search is already running for this occurrence.")
            if manual and source.review_status == ReviewStatus.SELECTED.value:
                raise InvalidSelectionError(
                    "Clear the current selection before searching again."
                )
            if manual:
                session.execute(
                    delete(AmazonCandidateRow).where(
                        AmazonCandidateRow.source_track_id == source_id
                    )
                )
                source.selected_candidate_id = None
                source.review_status = ReviewStatus.UNREVIEWED.value
                source.library_match = None
                source.queue_outcome = ImportQueueOutcome.NONE.value
                source.queued_job_id = None
                source.queued_duplicate_of_source_id = None
            source.matching_status = MatchingStatus.SEARCHING.value
            source.attempt_count += 1
            source.last_error = None
            source.updated_at = now
            _bump(import_row, now)

    def save_candidates(
        self,
        session_id: str,
        source_id: str,
        candidates: Sequence[CandidateDraft],
    ) -> None:
        now = self._clock()
        with self._write() as session:
            import_row = self._require_session(session, session_id)
            source = self._require_source(session, session_id, source_id)
            session.execute(
                delete(AmazonCandidateRow).where(
                    AmazonCandidateRow.source_track_id == source_id
                )
            )
            for candidate in candidates:
                session.add(
                    AmazonCandidateRow(
                        id=uuid.uuid4().hex,
                        source_track_id=source_id,
                        track_url=candidate.track_url,
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
                        created_at=now,
                    )
                )
            source.matching_status = (
                MatchingStatus.CANDIDATES_READY.value
                if candidates
                else MatchingStatus.NO_RESULTS.value
            )
            source.last_error = None
            source.updated_at = now
            _bump(import_row, now)

    def mark_source_failed(self, session_id: str, source_id: str, error: str) -> None:
        now = self._clock()
        with self._write() as session:
            import_row = self._require_session(session, session_id)
            source = self._require_source(session, session_id, source_id)
            source.matching_status = MatchingStatus.FAILED.value
            source.last_error = error
            source.updated_at = now
            _bump(import_row, now)

    def complete_matching_if_ready(self, session_id: str) -> bool:
        now = self._clock()
        with self._write() as session:
            row = self._require_session(session, session_id)
            if row.status != ImportStatus.MATCHING.value:
                return False
            statuses = session.scalars(
                select(SourceTrackRow.matching_status).where(
                    SourceTrackRow.session_id == session_id
                )
            ).all()
            if not statuses or any(status not in _TERMINAL_VALUES for status in statuses):
                return False
            row.status = ImportStatus.MATCHING_COMPLETE.value
            row.active_slot = None
            row.matching_completed_at = now
            _bump(row, now)
            return True

    def pause_session(self, session_id: str) -> ImportSession:
        now = self._clock()
        with self._write() as session:
            row = self._require_session(session, session_id)
            if row.status != ImportStatus.MATCHING.value:
                raise ImportStateError("Only a matching import can be paused.")
            row.status = ImportStatus.PAUSED.value
            _bump(row, now)
            return _to_session(row, self._counts(session, session_id))

    def resume_session(self, session_id: str) -> ImportSession:
        now = self._clock()
        with self._write() as session:
            row = self._require_session(session, session_id)
            if row.status != ImportStatus.PAUSED.value:
                raise ImportStateError("Only a paused import can be resumed.")
            row.status = ImportStatus.MATCHING.value
            _bump(row, now)
            return _to_session(row, self._counts(session, session_id))

    def select_candidate(
        self,
        session_id: str,
        source_id: str,
        candidate_id: str,
        *,
        library_match: LibraryMatch | None,
    ) -> None:
        now = self._clock()
        with self._write() as session:
            import_row = self._require_session(session, session_id)
            source = self._require_source(session, session_id, source_id)
            if import_row.status == ImportStatus.EXTRACTING.value:
                raise ImportStateError("This import is still extracting.")
            if source.queue_outcome in (
                ImportQueueOutcome.QUEUED.value,
                ImportQueueOutcome.DUPLICATE.value,
            ):
                raise ImportStateError("This occurrence has already been added to the queue.")
            candidate = session.scalar(
                select(AmazonCandidateRow.id).where(
                    AmazonCandidateRow.id == candidate_id,
                    AmazonCandidateRow.source_track_id == source_id,
                )
            )
            if candidate is None:
                raise InvalidSelectionError("The selected Amazon candidate is not available.")
            source.selected_candidate_id = candidate_id
            source.review_status = ReviewStatus.SELECTED.value
            source.library_match = library_match.value if library_match else None
            source.queue_outcome = ImportQueueOutcome.NONE.value
            source.queued_job_id = None
            source.queued_duplicate_of_source_id = None
            source.updated_at = now
            _bump(import_row, now)

    def skip_source(self, session_id: str, source_id: str) -> None:
        now = self._clock()
        with self._write() as session:
            import_row = self._require_session(session, session_id)
            source = self._require_source(session, session_id, source_id)
            if source.queue_outcome in (
                ImportQueueOutcome.QUEUED.value,
                ImportQueueOutcome.DUPLICATE.value,
            ):
                raise ImportStateError("This occurrence has already been added to the queue.")
            source.selected_candidate_id = None
            source.review_status = ReviewStatus.SKIPPED.value
            source.library_match = None
            source.queue_outcome = ImportQueueOutcome.NONE.value
            source.queued_job_id = None
            source.queued_duplicate_of_source_id = None
            source.updated_at = now
            _bump(import_row, now)

    def record_queue_outcome(
        self,
        session_id: str,
        source_id: str,
        *,
        outcome: ImportQueueOutcome,
        job_id: str | None,
        library_match: LibraryMatch | None,
        duplicate_of_source_id: str | None = None,
    ) -> None:
        now = self._clock()
        with self._write() as session:
            import_row = self._require_session(session, session_id)
            source = self._require_source(session, session_id, source_id)
            source.queue_outcome = outcome.value
            source.queued_job_id = job_id
            source.library_match = library_match.value if library_match else None
            source.queued_duplicate_of_source_id = duplicate_of_source_id
            source.updated_at = now
            _bump(import_row, now)

    def _counts(self, session: Session, session_id: str) -> ImportCounts:
        rows = session.scalars(
            select(SourceTrackRow).where(SourceTrackRow.session_id == session_id)
        ).all()
        return _counts_from_rows(rows)

    @staticmethod
    def _require_session(session: Session, session_id: str) -> ImportSessionRow:
        row = session.get(ImportSessionRow, session_id)
        if row is None:
            raise ImportNotFoundError("Import session not found.")
        return row

    @staticmethod
    def _require_source(
        session: Session,
        session_id: str,
        source_id: str,
    ) -> SourceTrackRow:
        row = session.scalar(
            select(SourceTrackRow).where(
                SourceTrackRow.id == source_id,
                SourceTrackRow.session_id == session_id,
            )
        )
        if row is None:
            raise ImportNotFoundError("Source track not found.")
        return row
