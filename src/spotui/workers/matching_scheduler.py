"""Bounded background matching for the single active Spotify import."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from spotui.domain.errors import CatalogError, ImportNotFoundError, ImportStateError
from spotui.persistence.repositories.imports import ImportRepository
from spotui.services.matching import MatchingService

logger = logging.getLogger("spotui.imports.matching")


@dataclass(slots=True)
class _SessionControl:
    pause: threading.Event = field(default_factory=threading.Event)
    cancel: threading.Event = field(default_factory=threading.Event)
    wake: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class MatchingWorker:
    """One coordinator per active import, with globally bounded searches."""

    def __init__(
        self,
        repository: ImportRepository,
        matching: MatchingService,
        *,
        concurrency: int = 3,
        join_timeout_seconds: float = 5.0,
    ) -> None:
        self._repository = repository
        self._matching = matching
        self._concurrency = max(1, min(5, concurrency))
        self._join_timeout_seconds = join_timeout_seconds
        self._stop = threading.Event()
        self._controls: dict[str, _SessionControl] = {}
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop.clear()
        for session_id in self._repository.recover_interrupted_imports():
            self.start_session(session_id)

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            controls = list(self._controls.items())
        for _session_id, control in controls:
            control.wake.set()
        for _session_id, control in controls:
            if control.thread is not None:
                control.thread.join(self._join_timeout_seconds)
                if control.thread.is_alive():
                    logger.warning("matching coordinator did not stop in time")

    def start_session(self, session_id: str) -> None:
        with self._lock:
            existing = self._controls.get(session_id)
            if existing is not None:
                existing.pause.clear()
                existing.wake.set()
                return
            control = _SessionControl()
            thread = threading.Thread(
                target=self._coordinate,
                args=(session_id, control),
                name=f"spotui-matching-{session_id[:8]}",
                daemon=True,
            )
            control.thread = thread
            self._controls[session_id] = control
            thread.start()

    def pause(self, session_id: str) -> None:
        with self._lock:
            control = self._controls.get(session_id)
        if control is not None:
            control.pause.set()
            control.wake.set()

    def resume(self, session_id: str) -> None:
        with self._lock:
            control = self._controls.get(session_id)
        if control is None:
            self.start_session(session_id)
            return
        control.pause.clear()
        control.wake.set()

    def cancel(self, session_id: str) -> None:
        with self._lock:
            control = self._controls.get(session_id)
        if control is not None:
            control.cancel.set()
            control.wake.set()

    def _coordinate(self, session_id: str, control: _SessionControl) -> None:
        executor = ThreadPoolExecutor(
            max_workers=self._concurrency,
            thread_name_prefix="spotui-match",
        )
        inflight: set[Future[None]] = set()
        try:
            while not self._stop.is_set() and not control.cancel.is_set():
                if control.pause.is_set():
                    control.wake.wait(0.25)
                    control.wake.clear()
                    continue
                if not self._repository.session_is_matching(session_id):
                    break
                self._schedule(session_id, control, executor, inflight)
                if inflight:
                    done, inflight = wait(
                        inflight,
                        timeout=0.25,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in done:
                        try:
                            future.result()
                        except Exception:
                            logger.exception("matching task failed")
                    continue
                if self._repository.complete_matching_if_ready(session_id):
                    logger.info("import %s matching complete", session_id)
                    break
                control.wake.wait(0.25)
                control.wake.clear()
        except Exception:
            logger.exception("matching coordinator failed for import %s", session_id)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            with self._lock:
                if self._controls.get(session_id) is control:
                    self._controls.pop(session_id, None)

    def _schedule(
        self,
        session_id: str,
        control: _SessionControl,
        executor: ThreadPoolExecutor,
        inflight: set[Future[None]],
    ) -> None:
        capacity = self._concurrency - len(inflight)
        if capacity <= 0:
            return
        pending = self._repository.pending_source_ids(session_id, limit=capacity)
        for source_id in pending:
            if (
                self._stop.is_set()
                or control.cancel.is_set()
                or control.pause.is_set()
                or len(inflight) >= self._concurrency
            ):
                return
            try:
                self._repository.start_source_search(
                    session_id,
                    source_id,
                    manual=False,
                )
            except (ImportStateError, ImportNotFoundError):
                continue
            inflight.add(
                executor.submit(self._search_one, session_id, source_id, control)
            )

    def _search_one(
        self,
        session_id: str,
        source_id: str,
        control: _SessionControl,
    ) -> None:
        if self._stop.is_set() or control.cancel.is_set():
            return
        try:
            title, artist, duration = self._repository.source_search_data(
                session_id,
                source_id,
            )
            candidates = self._matching.find_candidates(
                title=title,
                artist=artist,
                duration_seconds=duration,
            )
        except CatalogError as exc:
            if not self._stop.is_set() and not control.cancel.is_set():
                self._record_failure(
                    session_id,
                    source_id,
                    str(exc).strip()[:300] or "Amazon matching failed.",
                )
            return
        except Exception:
            logger.exception("unexpected matching failure for %s", source_id)
            if not self._stop.is_set() and not control.cancel.is_set():
                self._record_failure(session_id, source_id, "Amazon matching failed.")
            return
        if self._stop.is_set() or control.cancel.is_set():
            return
        try:
            self._repository.save_candidates(session_id, source_id, candidates)
        except (ImportNotFoundError, ImportStateError):
            return
        control.wake.set()

    def _record_failure(self, session_id: str, source_id: str, error: str) -> None:
        try:
            self._repository.mark_source_failed(session_id, source_id, error)
        except (ImportNotFoundError, ImportStateError):
            pass
