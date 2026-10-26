"""Mutable runtime state shared by the app lifespan, services, and worker."""

from __future__ import annotations

from dataclasses import dataclass

from spotui.config import AppConfig
from spotui.paths import Paths
from spotui.persistence.database import Database
from spotui.server import Listener


@dataclass(slots=True)
class ApplicationRuntime:
    config: AppConfig
    paths: Paths
    listeners: tuple[Listener, ...] = ()
    database: Database | None = None
    started_at: float = 0.0
    stopping: bool = False
