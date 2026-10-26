"""Service container attached to the application runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from spotui.services.entity_details import EntityDetailsService
from spotui.services.queue import QueueService
from spotui.services.search import SearchService

logger = logging.getLogger("spotui.services")


class Closable(Protocol):
    def close(self) -> None: ...


@dataclass(slots=True)
class ApplicationServices:
    search: SearchService
    entity_details: EntityDetailsService
    queue: QueueService | None = None
    resources: tuple[Closable, ...] = ()
    _started: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False)

    def start(self) -> None:
        if self._started or self._closed:
            return
        self._started = True
        if self.queue is not None:
            self.queue.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.queue is not None:
            try:
                self.queue.stop()
            except Exception:
                logger.exception("failed to stop the download queue")
        for resource in self.resources:
            try:
                resource.close()
            except Exception:
                logger.exception("failed to release an application service resource")
