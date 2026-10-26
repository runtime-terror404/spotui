"""Service container attached to the application runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from spotui.services.entity_details import EntityDetailsService
from spotui.services.search import SearchService

logger = logging.getLogger("spotui.services")


class Closable(Protocol):
    def close(self) -> None: ...


@dataclass(slots=True)
class ApplicationServices:
    search: SearchService
    entity_details: EntityDetailsService
    resources: tuple[Closable, ...] = ()
    _closed: bool = field(default=False, init=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for resource in self.resources:
            try:
                resource.close()
            except Exception:
                logger.exception("failed to release an application service resource")
