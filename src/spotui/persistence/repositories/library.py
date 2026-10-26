"""Transactional access to configured library roots, files, and scan runs."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from spotui.domain.library import (
    LibraryFileMetadata,
    LibraryLookupResult,
    LibraryMatch,
    LibraryRoot,
    LibraryScan,
    LibraryScanStatus,
)
from spotui.persistence.models import LibraryFile as LibraryFileRow
from spotui.persistence.models import LibraryRoot as LibraryRootRow
from spotui.persistence.models import LibraryScanRun as LibraryScanRow


def _epoch() -> int:
    return int(time.time())


def _to_root(row: LibraryRootRow) -> LibraryRoot:
    return LibraryRoot(
        id=row.id,
        path=row.path,
        available=row.available,
        index_complete=row.index_complete,
        last_checked_at=row.last_checked_at,
        last_scan_at=row.last_scan_at,
        file_count=row.file_count,
        last_error=row.last_error,
    )


def _to_scan(row: LibraryScanRow) -> LibraryScan:
    return LibraryScan(
        id=row.id,
        root_id=row.root_id,
        status=LibraryScanStatus(row.status),
        started_at=row.started_at,
        finished_at=row.finished_at,
        files_seen=row.files_seen,
        files_indexed=row.files_indexed,
        files_removed=row.files_removed,
        files_failed=row.files_failed,
        error=row.error,
    )


class LibraryRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], int] = _epoch,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def reconcile_roots(self, configured_paths: Sequence[str]) -> tuple[LibraryRoot, ...]:
        now = self._clock()
        desired = set(configured_paths)
        with self._session_factory.begin() as session:
            rows = list(session.scalars(select(LibraryRootRow)))
            existing = {row.path for row in rows}
            for row in rows:
                if row.path not in desired:
                    session.delete(row)
            for path in sorted(desired - existing):
                session.add(
                    LibraryRootRow(
                        path=path,
                        available=False,
                        index_complete=False,
                        last_checked_at=None,
                        last_scan_at=None,
                        file_count=0,
                        last_error=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            current = session.scalars(select(LibraryRootRow)).all()
            return tuple(_to_root(row) for row in sorted(current, key=lambda item: item.path))

    def list_roots(self) -> tuple[LibraryRoot, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(LibraryRootRow).order_by(LibraryRootRow.path.asc())
            ).all()
            return tuple(_to_root(row) for row in rows)

    def update_root_availability(
        self,
        root_id: int,
        *,
        available: bool,
        error: str | None = None,
    ) -> LibraryRoot:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = session.get(LibraryRootRow, root_id)
            if row is None:
                raise LookupError("Library root not found.")
            row.available = available
            row.last_checked_at = now
            row.last_error = error
            if not available:
                row.index_complete = False
            row.updated_at = now
            return _to_root(row)

    def recover_interrupted_scans(self) -> int:
        now = self._clock()
        with self._session_factory.begin() as session:
            rows = session.scalars(
                select(LibraryScanRow).where(
                    LibraryScanRow.status == LibraryScanStatus.RUNNING.value
                )
            ).all()
            for row in rows:
                row.status = LibraryScanStatus.INTERRUPTED.value
                row.finished_at = now
                row.error = "Library scan interrupted by application restart."
                root = session.get(LibraryRootRow, row.root_id)
                if root is not None:
                    root.index_complete = False
                    root.updated_at = now
            return len(rows)

    def begin_scan(self, root_id: int) -> LibraryScan:
        now = self._clock()
        with self._session_factory.begin() as session:
            if session.get(LibraryRootRow, root_id) is None:
                raise LookupError("Library root not found.")
            row = LibraryScanRow(
                root_id=root_id,
                status=LibraryScanStatus.RUNNING.value,
                started_at=now,
                finished_at=None,
                files_seen=0,
                files_indexed=0,
                files_removed=0,
                files_failed=0,
                error=None,
            )
            session.add(row)
            session.flush()
            return _to_scan(row)

    def file_state(self, root_id: int) -> dict[str, tuple[int, int, int]]:
        """Return path -> (id, size, modification time in ns) for a root."""
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    LibraryFileRow.id,
                    LibraryFileRow.path,
                    LibraryFileRow.size_bytes,
                    LibraryFileRow.modified_at_ns,
                ).where(LibraryFileRow.root_id == root_id)
            ).all()
            return {
                path: (file_id, size_bytes, modified_at_ns)
                for file_id, path, size_bytes, modified_at_ns in rows
            }

    def apply_scan_batch(
        self,
        scan_id: int,
        root_id: int,
        *,
        files: Sequence[LibraryFileMetadata],
        unchanged_ids: Sequence[int],
        files_seen: int,
        files_indexed: int,
        files_failed: int,
    ) -> None:
        now = self._clock()
        with self._session_factory.begin() as session:
            scan = session.get(LibraryScanRow, scan_id)
            if scan is None or scan.status != LibraryScanStatus.RUNNING.value:
                raise LookupError("Library scan is no longer running.")
            if files:
                rows = [
                    {
                        "root_id": root_id,
                        "path": file.path,
                        "filename": file.filename,
                        "extension": file.extension,
                        "size_bytes": file.size_bytes,
                        "modified_at_ns": file.modified_at_ns,
                        "title": file.title,
                        "artist": file.artist,
                        "album": file.album,
                        "track_number": file.track_number,
                        "duration_seconds": file.duration_seconds,
                        "metadata_source": file.metadata_source.value,
                        "normalized_title": file.normalized_title,
                        "normalized_artist": file.normalized_artist,
                        "amazon_track_key": file.amazon_track_key,
                        "last_seen_scan_id": scan_id,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for file in files
                ]
                statement = sqlite_insert(LibraryFileRow).values(rows)
                statement = statement.on_conflict_do_update(
                    index_elements=["root_id", "path"],
                    set_={
                        "filename": statement.excluded.filename,
                        "extension": statement.excluded.extension,
                        "size_bytes": statement.excluded.size_bytes,
                        "modified_at_ns": statement.excluded.modified_at_ns,
                        "title": statement.excluded.title,
                        "artist": statement.excluded.artist,
                        "album": statement.excluded.album,
                        "track_number": statement.excluded.track_number,
                        "duration_seconds": statement.excluded.duration_seconds,
                        "metadata_source": statement.excluded.metadata_source,
                        "normalized_title": statement.excluded.normalized_title,
                        "normalized_artist": statement.excluded.normalized_artist,
                        "amazon_track_key": statement.excluded.amazon_track_key,
                        "last_seen_scan_id": statement.excluded.last_seen_scan_id,
                        "updated_at": statement.excluded.updated_at,
                    },
                )
                session.execute(statement)
            if unchanged_ids:
                session.execute(
                    update(LibraryFileRow)
                    .where(LibraryFileRow.id.in_(unchanged_ids))
                    .values(last_seen_scan_id=scan_id, updated_at=now)
                )
            scan.files_seen = files_seen
            scan.files_indexed = files_indexed
            scan.files_failed = files_failed

    def finish_scan(
        self,
        scan_id: int,
        root_id: int,
        *,
        status: LibraryScanStatus,
        files_seen: int,
        files_indexed: int,
        files_failed: int,
        available: bool,
        error: str | None,
        remove_unseen: bool,
    ) -> LibraryScan:
        if status is LibraryScanStatus.RUNNING:
            raise ValueError("a finished scan cannot remain running")
        now = self._clock()
        with self._session_factory.begin() as session:
            scan = session.get(LibraryScanRow, scan_id)
            root = session.get(LibraryRootRow, root_id)
            if scan is None:
                raise LookupError("Library scan not found.")
            if root is None:
                raise LookupError("Library root not found.")
            removed = 0
            if remove_unseen and status is LibraryScanStatus.COMPLETED:
                result = session.execute(
                    delete(LibraryFileRow).where(
                        LibraryFileRow.root_id == root_id,
                        or_(
                            LibraryFileRow.last_seen_scan_id.is_(None),
                            LibraryFileRow.last_seen_scan_id != scan_id,
                        ),
                    )
                )
                removed = result.rowcount or 0
            file_count = session.scalar(
                select(func.count())
                .select_from(LibraryFileRow)
                .where(LibraryFileRow.root_id == root_id)
            )
            scan.status = status.value
            scan.finished_at = now
            scan.files_seen = max(files_seen, 0)
            scan.files_indexed = max(files_indexed, 0)
            scan.files_removed = removed
            scan.files_failed = max(files_failed, 0)
            scan.error = error
            root.available = available
            root.index_complete = available and status is LibraryScanStatus.COMPLETED
            root.last_checked_at = now
            if status is LibraryScanStatus.COMPLETED:
                root.last_scan_at = now
            root.file_count = int(file_count or 0)
            root.last_error = error
            root.updated_at = now
            return _to_scan(scan)

    def active_scan(self) -> LibraryScan | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(LibraryScanRow)
                .where(LibraryScanRow.status == LibraryScanStatus.RUNNING.value)
                .order_by(LibraryScanRow.started_at.desc())
                .limit(1)
            ).first()
            return _to_scan(row) if row is not None else None

    def lookup(
        self,
        *,
        amazon_track_key: str | None,
        normalized_title: str,
        artist_tokens: frozenset[str],
    ) -> LibraryLookupResult:
        with self._session_factory() as session:
            roots = session.scalars(select(LibraryRootRow)).all()
            complete = all(root.available and root.index_complete for root in roots)
            if amazon_track_key and session.scalar(
                select(LibraryFileRow.id)
                .where(LibraryFileRow.amazon_track_key == amazon_track_key)
                .limit(1)
            ):
                return LibraryLookupResult(LibraryMatch.EXACT, complete)
            if not normalized_title:
                return LibraryLookupResult(None, complete)
            stored_artists = session.scalars(
                select(LibraryFileRow.normalized_artist)
                .where(LibraryFileRow.normalized_title == normalized_title)
                .distinct()
            ).all()
            if not artist_tokens:
                if stored_artists:
                    return LibraryLookupResult(LibraryMatch.LIKELY, complete)
            else:
                for stored in stored_artists:
                    if artist_tokens & set(stored.split()):
                        return LibraryLookupResult(LibraryMatch.LIKELY, complete)
            return LibraryLookupResult(None, complete)
