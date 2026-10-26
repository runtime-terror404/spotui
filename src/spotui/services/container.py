"""Service container attached to the application runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from spotui.services.entity_details import EntityDetailsService
from spotui.services.imports import ImportService
from spotui.services.library import LibraryService
from spotui.services.now_playing import NowPlayingService
from spotui.services.queue import QueueService
from spotui.services.search import SearchService
from spotui.services.system_info import SystemInfoService
from spotui.services.trusted_devices import TrustedDeviceService

logger = logging.getLogger("spotui.services")


class Closable(Protocol):
    def close(self) -> None: ...


@dataclass(slots=True)
class ApplicationServices:
    search: SearchService
    entity_details: EntityDetailsService
    queue: QueueService | None = None
    now_playing: NowPlayingService | None = None
    library: LibraryService | None = None
    imports: ImportService | None = None
    trusted_devices: TrustedDeviceService | None = None
    system_info: SystemInfoService | None = None
    resources: tuple[Closable, ...] = ()
    _started: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False)

    def start(self) -> None:
        if self._started or self._closed:
            return
        self._started = True
        if self.library is not None:
            self.library.start()
        if self.queue is not None:
            self.queue.start()
        if self.imports is not None:
            self.imports.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.imports is not None:
            try:
                self.imports.close()
            except Exception:
                logger.exception("failed to stop Spotify matching")
        if self.queue is not None:
            try:
                self.queue.stop()
            except Exception:
                logger.exception("failed to stop the download queue")
        if self.library is not None:
            try:
                self.library.close()
            except Exception:
                logger.exception("failed to stop the library scanner")
        for resource in self.resources:
            try:
                resource.close()
            except Exception:
                logger.exception("failed to release an application service resource")
