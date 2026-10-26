"""Background scanning for the durable read-only library index."""

from __future__ import annotations

import logging
import os
import stat
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from spotui.domain.library import (
    LibraryFileMetadata,
    LibraryMetadataSource,
    LibraryRoot,
    LibraryScanStatus,
    artist_from_path,
    normalize_library_text,
    title_from_filename,
)
from spotui.persistence.repositories.library import LibraryRepository
from spotui.providers.audio_tags.base import AudioTagMetadata, AudioTagReader

logger = logging.getLogger("spotui.library.scanner")

AUDIO_EXTENSIONS = frozenset(
    {
        ".aif",
        ".aiff",
        ".flac",
        ".m4a",
        ".mp3",
        ".mp4",
        ".oga",
        ".ogg",
        ".opus",
        ".wav",
        ".wma",
    }
)
_SCAN_BATCH_SIZE = 200


def _is_readable_directory(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.R_OK | os.X_OK)
    except OSError:
        return False


class LibraryScanWorker:
    """One background scanner; scans roots sequentially and never writes media."""

    def __init__(
        self,
        repository: LibraryRepository,
        tag_reader: AudioTagReader,
        root_paths: Sequence[str],
        *,
        refresh_seconds: int = 3600,
        scan_on_startup: bool = True,
        clock: Callable[[], float] = time.monotonic,
        join_timeout_seconds: float = 5.0,
        batch_size: int = _SCAN_BATCH_SIZE,
    ) -> None:
        self._repository = repository
        self._tag_reader = tag_reader
        self._root_paths = tuple(root_paths)
        self._refresh_seconds = refresh_seconds
        self._scan_on_startup = scan_on_startup
        self._clock = clock
        self._join_timeout_seconds = join_timeout_seconds
        self._batch_size = max(1, batch_size)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._scan_requested = threading.Event()
        self._scan_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.prepare()
        self._thread = threading.Thread(
            target=self._run,
            name="spotui-library-scanner",
            daemon=True,
        )
        self._thread.start()

    def prepare(self) -> None:
        """Reconcile configured roots and detect mounts unavailable at startup."""
        self._repository.reconcile_roots(self._root_paths)
        self._repository.recover_interrupted_scans()
        for root in self._repository.list_roots():
            available = _is_readable_directory(Path(root.path))
            self._repository.update_root_availability(
                root.id,
                available=available,
                error=None if available else "Library root is unavailable.",
            )

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(self._join_timeout_seconds)
            if thread.is_alive():
                logger.warning("library scanner did not stop within its shutdown grace period")

    def request_scan(self) -> bool:
        if not self._root_paths:
            return False
        self._scan_requested.set()
        self._wake.set()
        return True

    def scan_all(self) -> bool:
        if not self._scan_lock.acquire(blocking=False):
            return False
        try:
            for root in self._repository.list_roots():
                if self._stop.is_set():
                    break
                self._scan_root(root)
            return True
        finally:
            self._scan_lock.release()

    def _run(self) -> None:
        next_due = (
            self._clock()
            if self._scan_on_startup
            else (
                self._clock() + self._refresh_seconds
                if self._refresh_seconds > 0
                else None
            )
        )
        while not self._stop.is_set():
            requested = self._scan_requested.is_set()
            due = next_due is not None and self._clock() >= next_due
            if requested or due:
                self._scan_requested.clear()
                try:
                    self.scan_all()
                except Exception:
                    logger.exception("library scan cycle failed")
                next_due = (
                    self._clock() + self._refresh_seconds
                    if self._refresh_seconds > 0
                    else None
                )
                continue
            timeout = None if next_due is None else max(0.0, next_due - self._clock())
            self._wake.wait(timeout)
            self._wake.clear()

    def _scan_root(self, root: LibraryRoot) -> None:
        path = Path(root.path)
        scan = self._repository.begin_scan(root.id)
        if not _is_readable_directory(path):
            self._finish_failed(
                scan.id,
                root,
                error="Library root is unavailable.",
                available=False,
            )
            logger.warning("library root unavailable: %s", root.path)
            return

        existing = self._repository.file_state(root.id)
        files: list[LibraryFileMetadata] = []
        unchanged_ids: list[int] = []
        files_seen = files_indexed = files_failed = 0
        traversal_errors: list[OSError] = []

        def on_walk_error(error: OSError) -> None:
            traversal_errors.append(error)

        def flush() -> None:
            nonlocal files, unchanged_ids
            if not files and not unchanged_ids:
                return
            self._repository.apply_scan_batch(
                scan.id,
                root.id,
                files=files,
                unchanged_ids=unchanged_ids,
                files_seen=files_seen,
                files_indexed=files_indexed,
                files_failed=files_failed,
            )
            files = []
            unchanged_ids = []

        try:
            for current, dirnames, filenames in os.walk(
                path,
                topdown=True,
                onerror=on_walk_error,
                followlinks=False,
            ):
                if self._stop.is_set():
                    break
                current_path = Path(current)
                dirnames[:] = sorted(
                    directory
                    for directory in dirnames
                    if not directory.startswith(".")
                    and not (current_path / directory).is_symlink()
                )
                for filename in sorted(filenames):
                    if self._stop.is_set():
                        break
                    if filename.startswith("."):
                        continue
                    file_path = current_path / filename
                    if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue
                    if file_path.is_symlink():
                        continue
                    try:
                        file_stat = file_path.stat()
                    except OSError:
                        files_failed += 1
                        continue
                    if not stat.S_ISREG(file_stat.st_mode):
                        continue
                    files_seen += 1
                    previous = existing.get(str(file_path))
                    if (
                        previous is not None
                        and previous[1] == file_stat.st_size
                        and previous[2] == file_stat.st_mtime_ns
                    ):
                        unchanged_ids.append(previous[0])
                    else:
                        try:
                            tags = self._tag_reader.read(file_path)
                        except Exception:
                            logger.debug(
                                "audio tag reader failed for %s",
                                file_path,
                                exc_info=True,
                            )
                            tags = AudioTagMetadata()
                        files.append(self._metadata(path, file_path, file_stat, tags))
                        files_indexed += 1
                    if len(files) + len(unchanged_ids) >= self._batch_size:
                        flush()
                if self._stop.is_set():
                    break
            if self._stop.is_set():
                flush()
                self._repository.finish_scan(
                    scan.id,
                    root.id,
                    status=LibraryScanStatus.INTERRUPTED,
                    files_seen=files_seen,
                    files_indexed=files_indexed,
                    files_failed=files_failed,
                    available=_is_readable_directory(path),
                    error="Library scan interrupted by shutdown.",
                    remove_unseen=False,
                )
                return

            flush()
            if traversal_errors or files_failed:
                error = "Some library files or directories could not be read."
                self._repository.finish_scan(
                    scan.id,
                    root.id,
                    status=LibraryScanStatus.FAILED,
                    files_seen=files_seen,
                    files_indexed=files_indexed,
                    files_failed=files_failed,
                    available=_is_readable_directory(path),
                    error=error,
                    remove_unseen=False,
                )
                logger.warning(
                    "library scan incomplete for %s: %s directory errors, %s file errors",
                    root.path,
                    len(traversal_errors),
                    files_failed,
                )
                return

            if not _is_readable_directory(path):
                self._finish_failed(
                    scan.id,
                    root,
                    error="Library root became unavailable during the scan.",
                    available=False,
                    files_seen=files_seen,
                    files_indexed=files_indexed,
                    files_failed=files_failed,
                )
                return

            result = self._repository.finish_scan(
                scan.id,
                root.id,
                status=LibraryScanStatus.COMPLETED,
                files_seen=files_seen,
                files_indexed=files_indexed,
                files_failed=files_failed,
                available=True,
                error=None,
                remove_unseen=True,
            )
            logger.info(
                "library scan complete for %s: %s seen, %s indexed, %s removed",
                root.path,
                result.files_seen,
                result.files_indexed,
                result.files_removed,
            )
        except Exception:
            logger.exception("library scan failed for %s", root.path)
            try:
                self._finish_failed(
                    scan.id,
                    root,
                    error="Library scan failed.",
                    available=_is_readable_directory(path),
                    files_seen=files_seen,
                    files_indexed=files_indexed,
                    files_failed=files_failed,
                )
            except Exception:
                logger.exception("failed to record the library scan failure")

    def _finish_failed(
        self,
        scan_id: int,
        root: LibraryRoot,
        *,
        error: str,
        available: bool,
        files_seen: int = 0,
        files_indexed: int = 0,
        files_failed: int = 0,
    ) -> None:
        self._repository.finish_scan(
            scan_id,
            root.id,
            status=LibraryScanStatus.FAILED,
            files_seen=files_seen,
            files_indexed=files_indexed,
            files_failed=files_failed,
            available=available,
            error=error,
            remove_unseen=False,
        )

    @staticmethod
    def _metadata(
        root: Path,
        path: Path,
        file_stat: os.stat_result,
        tags: AudioTagMetadata,
    ) -> LibraryFileMetadata:
        title = tags.title.strip() or title_from_filename(path)
        artist = tags.artist.strip() or artist_from_path(root, path, title)
        source = (
            LibraryMetadataSource.TAGS
            if tags.title.strip() or tags.artist.strip()
            else LibraryMetadataSource.FILENAME
        )
        return LibraryFileMetadata(
            path=str(path),
            filename=path.name,
            extension=path.suffix.lower().lstrip("."),
            size_bytes=file_stat.st_size,
            modified_at_ns=file_stat.st_mtime_ns,
            title=title,
            artist=artist,
            album=tags.album.strip(),
            track_number=tags.track_number.strip(),
            duration_seconds=tags.duration_seconds,
            metadata_source=source,
            normalized_title=normalize_library_text(title),
            normalized_artist=normalize_library_text(artist),
            amazon_track_key=tags.amazon_track_key,
        )
