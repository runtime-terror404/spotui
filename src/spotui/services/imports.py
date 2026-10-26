"""Spotify import extraction, review, and add-selected orchestration."""

from __future__ import annotations

import logging

from spotui.domain.errors import (
    CatalogError,
    ImportNotFoundError,
    ImportStateError,
    InvalidSelectionError,
)
from spotui.domain.imports import (
    AmazonCandidate,
    ImportEnqueueResult,
    ImportQueueOutcome,
    ImportSession,
    ImportSessionDetail,
    ImportSourceTrack,
    ImportStatus,
    ReviewStatus,
)
from spotui.domain.jobs import DownloadRequest
from spotui.domain.library import LibraryMatch
from spotui.domain.spotify import parse_spotify_link
from spotui.persistence.repositories.imports import ImportRepository
from spotui.providers.library.base import LibraryLookup
from spotui.providers.spotify.base import SpotifyProvider
from spotui.services.matching import MatchingService
from spotui.services.queue import QueueService
from spotui.workers.matching_scheduler import MatchingWorker

logger = logging.getLogger("spotui.imports")


class ImportService:
    def __init__(
        self,
        repository: ImportRepository,
        spotify: SpotifyProvider,
        matching: MatchingService,
        matching_worker: MatchingWorker,
        queue: QueueService,
        *,
        library: LibraryLookup | None = None,
    ) -> None:
        self._repository = repository
        self._spotify = spotify
        self._matching = matching
        self._matching_worker = matching_worker
        self._queue = queue
        self._library = library

    def start(self) -> None:
        self._matching_worker.start()

    def close(self) -> None:
        self._matching_worker.close()

    def create(self, url: str) -> ImportSessionDetail:
        link = parse_spotify_link(url)
        session = self._repository.create_extracting_session(link.original)
        try:
            collection = self._spotify.extract(link.original)
            self._repository.save_extraction(session.id, collection)
        except Exception:
            try:
                self._repository.delete_session(session.id)
            except ImportNotFoundError:
                pass
            raise
        self._matching_worker.start_session(session.id)
        return self._repository.get_session_detail(session.id)

    def list_sessions(self) -> tuple[ImportSession, ...]:
        return self._repository.list_sessions()

    def get(self, session_id: str) -> ImportSessionDetail:
        return self._repository.get_session_detail(session_id)

    def session_revision(self, session_id: str) -> int | None:
        return self._repository.session_revision(session_id)

    def pause(self, session_id: str) -> ImportSessionDetail:
        self._repository.pause_session(session_id)
        self._matching_worker.pause(session_id)
        return self._repository.get_session_detail(session_id)

    def resume(self, session_id: str) -> ImportSessionDetail:
        self._repository.resume_session(session_id)
        self._matching_worker.resume(session_id)
        return self._repository.get_session_detail(session_id)

    def cancel(self, session_id: str) -> None:
        session = self._repository.get_session(session_id)
        if session.status is ImportStatus.MATCHING_COMPLETE:
            raise ImportStateError("Completed imports must be deleted, not cancelled.")
        self._matching_worker.cancel(session_id)
        self._repository.delete_session(session_id)
        logger.info("cancelled Spotify import %s", session_id)

    def delete(self, session_id: str) -> None:
        self._repository.delete_session(
            session_id,
            require_status=ImportStatus.MATCHING_COMPLETE,
        )

    def select_candidate(
        self,
        session_id: str,
        source_id: str,
        candidate_id: str,
    ) -> ImportSessionDetail:
        detail = self._repository.get_session_detail(session_id)
        source = self._source(detail, source_id)
        candidate = self._candidate(source, candidate_id)
        library_match = self._library_match(candidate)
        self._repository.select_candidate(
            session_id,
            source_id,
            candidate_id,
            library_match=library_match,
        )
        return self._repository.get_session_detail(session_id)

    def skip_source(self, session_id: str, source_id: str) -> ImportSessionDetail:
        self._repository.skip_source(session_id, source_id)
        return self._repository.get_session_detail(session_id)

    def search_source(self, session_id: str, source_id: str) -> ImportSessionDetail:
        detail = self._repository.get_session_detail(session_id)
        source = self._source(detail, source_id)
        self._repository.start_source_search(session_id, source_id, manual=True)
        try:
            candidates = self._matching.find_candidates(
                title=source.title,
                artist=source.artist,
                duration_seconds=source.duration_seconds,
            )
        except CatalogError as exc:
            self._mark_search_failure(session_id, source_id, exc)
            raise
        except Exception:
            self._mark_search_failure(
                session_id,
                source_id,
                RuntimeError("Amazon matching failed."),
            )
            raise
        self._repository.save_candidates(session_id, source_id, candidates)
        return self._repository.get_session_detail(session_id)

    def enqueue_selected(
        self,
        session_id: str,
        *,
        force_library: bool = False,
    ) -> ImportEnqueueResult:
        detail = self._repository.get_session_detail(session_id)
        if detail.session.status is ImportStatus.EXTRACTING:
            raise ImportStateError("This import is still extracting.")
        self._queue.ensure_available()
        key_owners: dict[str, str] = {}
        selected = [
            source
            for source in detail.sources
            if source.review_status is ReviewStatus.SELECTED
            and source.selected_candidate_id is not None
        ]
        for source in selected:
            candidate = self._selected_candidate(source)
            if candidate is None:
                continue
            if source.queue_outcome in (
                ImportQueueOutcome.QUEUED,
                ImportQueueOutcome.DUPLICATE,
            ):
                key_owners.setdefault(candidate.track_key, source.id)

        added = duplicate = skipped_library = 0
        for source in selected:
            candidate = self._selected_candidate(source)
            if candidate is None:
                continue
            if source.queue_outcome in (
                ImportQueueOutcome.QUEUED,
                ImportQueueOutcome.DUPLICATE,
            ):
                continue
            library_match = self._library_match(candidate)
            if library_match is not None and not force_library:
                if source.queue_outcome is not ImportQueueOutcome.SKIPPED_LIBRARY:
                    self._repository.record_queue_outcome(
                        session_id,
                        source.id,
                        outcome=ImportQueueOutcome.SKIPPED_LIBRARY,
                        job_id=None,
                        library_match=library_match,
                    )
                    skipped_library += 1
                continue
            owner = key_owners.get(candidate.track_key)
            if owner is None:
                key_owners[candidate.track_key] = source.id
            result = self._queue.enqueue(
                DownloadRequest(
                    url=candidate.track_url,
                    title=candidate.title,
                    artist=candidate.artist,
                    source_import_id=session_id,
                    source_occurrence_id=source.id,
                    source_playlist_title=detail.session.title,
                )
            )
            owns_existing_job = (
                result.job.source_import_id == session_id
                and result.job.source_occurrence_id == source.id
            )
            outcome = (
                ImportQueueOutcome.QUEUED
                if not result.duplicate or owns_existing_job
                else ImportQueueOutcome.DUPLICATE
            )
            self._repository.record_queue_outcome(
                session_id,
                source.id,
                outcome=outcome,
                job_id=result.job.id,
                library_match=library_match,
                duplicate_of_source_id=owner,
            )
            if outcome is ImportQueueOutcome.DUPLICATE:
                duplicate += 1
            else:
                added += 1
        return ImportEnqueueResult(
            detail=self._repository.get_session_detail(session_id),
            queued=added,
            duplicate=duplicate,
            skipped_library=skipped_library,
        )

    def _mark_search_failure(
        self,
        session_id: str,
        source_id: str,
        exc: Exception,
    ) -> None:
        error = str(exc).strip()[:300] or "Amazon matching failed."
        try:
            self._repository.mark_source_failed(session_id, source_id, error)
        except ImportNotFoundError:
            pass

    def _library_match(self, candidate: AmazonCandidate) -> LibraryMatch | None:
        if self._library is None:
            return None
        return self._library.lookup(
            candidate.track_url,
            candidate.title,
            candidate.artist,
        ).match

    @staticmethod
    def _source(detail: ImportSessionDetail, source_id: str) -> ImportSourceTrack:
        source = next((item for item in detail.sources if item.id == source_id), None)
        if source is None:
            raise ImportNotFoundError("Source track not found.")
        return source

    @staticmethod
    def _candidate(source: ImportSourceTrack, candidate_id: str) -> AmazonCandidate:
        candidate = next(
            (item for item in source.candidates if item.id == candidate_id),
            None,
        )
        if candidate is None:
            raise InvalidSelectionError("The selected Amazon candidate is not available.")
        return candidate

    @staticmethod
    def _selected_candidate(source: ImportSourceTrack) -> AmazonCandidate | None:
        return next(
            (
                item
                for item in source.candidates
                if item.id == source.selected_candidate_id
            ),
            None,
        )
