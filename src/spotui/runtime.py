"""Mutable runtime state shared by the app lifespan, services, and worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from spotui.config import AppConfig
from spotui.paths import Paths
from spotui.persistence.database import Database
from spotui.server import Listener

if TYPE_CHECKING:
    from spotui.services.container import ApplicationServices

ServicesFactory = Callable[[AppConfig, Paths, Database], "ApplicationServices"]


@dataclass(slots=True)
class ApplicationRuntime:
    config: AppConfig
    paths: Paths
    listeners: tuple[Listener, ...] = ()
    database: Database | None = None
    services: ApplicationServices | None = None
    services_factory: ServicesFactory | None = None
    started_at: float = 0.0
    stopping: bool = False
