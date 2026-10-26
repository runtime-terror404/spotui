"""Persistence for the one-time legacy JSON queue migration."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from spotui.domain.jobs import ACTIVE_JOB_STATES, JobState
from spotui.domain.legacy import LegacyImportOutcome, LegacyJobEntry
from spotui.persistence.models import DownloadJob as DownloadJobRow
from spotui.persistence.models import LegacyQueueImport as LegacyQueueImportRow


@dataclass(frozen=True, slots=True)
class PriorLegacyImport:
    outcome: LegacyImportOutcome
    job_id: str | None
    reason: str | None


def _epoch() -> int:
    return int(time.time())


class LegacyQueueRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], int] = _epoch,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def existing_imports(self, source_path: str) -> dict[str, PriorLegacyImport]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(LegacyQueueImportRow).where(
                    LegacyQueueImportRow.source_path == source_path
                )
            ).all()
        return {
            row.legacy_key: PriorLegacyImport(
                outcome=LegacyImportOutcome(row.outcome),
                job_id=row.job_id,
                reason=row.reason,
            )
            for row in rows
        }

    def active_jobs_by_track_key(self) -> dict[str, str]:
        active = tuple(state.value for state in ACTIVE_JOB_STATES)
        with self._session_factory() as session:
            rows = session.execute(
                select(DownloadJobRow.track_key, DownloadJobRow.id).where(
                    DownloadJobRow.state.in_(active)
                )
            ).all()
        return {str(track_key): str(job_id) for track_key, job_id in rows}

    def job_exists(self, job_id: str) -> bool:
        with self._session_factory() as session:
            return session.get(DownloadJobRow, job_id) is not None

    def import_entry(
        self,
        entry: LegacyJobEntry,
        *,
        source_path: str,
        job_id: str,
    ) -> None:
        now = self._clock()
        with self._session_factory.begin() as session:
            session.add(
                DownloadJobRow(
                    id=job_id,
                    track_url=entry.url,
                    track_key=entry.track_key,
                    title=entry.title,
                    artist=entry.artist,
                    state=entry.state.value,
                    status_message=entry.status_message,
                    progress_phase=None,
                    progress_percent=None,
                    attempt_count=_attempt_count(entry),
                    last_error=(
                        entry.status_message if entry.state is JobState.FAILED else None
                    ),
                    output_path=entry.output_path,
                    source_import_id=None,
                    source_occurrence_id=None,
                    source_playlist_title=None,
                    created_at=entry.added_at,
                    updated_at=entry.updated_at,
                    started_at=(
                        entry.added_at if entry.state is not JobState.QUEUED else None
                    ),
                    completed_at=_completed_at(entry),
                )
            )
            session.add(
                LegacyQueueImportRow(
                    source_path=source_path,
                    legacy_key=entry.legacy_key,
                    legacy_job_id=entry.legacy_id,
                    outcome=LegacyImportOutcome.IMPORTED.value,
                    reason="; ".join(entry.warnings) or None,
                    job_id=job_id,
                    imported_at=now,
                )
            )

    def record_outcome(
        self,
        *,
        source_path: str,
        entry: LegacyJobEntry,
        outcome: LegacyImportOutcome,
        reason: str | None,
        job_id: str | None = None,
    ) -> None:
        with self._session_factory.begin() as session:
            session.add(
                LegacyQueueImportRow(
                    source_path=source_path,
                    legacy_key=entry.legacy_key,
                    legacy_job_id=entry.legacy_id,
                    outcome=outcome.value,
                    reason=reason,
                    job_id=job_id,
                    imported_at=self._clock(),
                )
            )

    def record_unparsed(
        self,
        *,
        source_path: str,
        legacy_key: str,
        legacy_id: str | None,
        outcome: LegacyImportOutcome,
        reason: str | None,
    ) -> None:
        """Persist a record that could not be mapped to a job entry."""
        with self._session_factory.begin() as session:
            session.add(
                LegacyQueueImportRow(
                    source_path=source_path,
                    legacy_key=legacy_key,
                    legacy_job_id=legacy_id,
                    outcome=outcome.value,
                    reason=reason,
                    job_id=None,
                    imported_at=self._clock(),
                )
            )


def _attempt_count(entry: LegacyJobEntry) -> int:
    if entry.state in (JobState.QUEUED, JobState.CANCELLED):
        return 0
    return 1


def _completed_at(entry: LegacyJobEntry) -> int | None:
    if entry.state is JobState.COMPLETED:
        return entry.finished_at or entry.updated_at
    if entry.state in (JobState.FAILED, JobState.CANCELLED, JobState.INTERRUPTED):
        return entry.updated_at
    return None
