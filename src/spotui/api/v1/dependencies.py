"""Shared API dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from spotui.domain.errors import (
    CatalogUnavailableError,
    LibraryUnavailableError,
    NowPlayingUnavailableError,
    QueueUnavailableError,
)
from spotui.services.container import ApplicationServices
from spotui.services.library import LibraryService
from spotui.services.now_playing import NowPlayingService
from spotui.services.queue import QueueService


def get_services(request: Request) -> ApplicationServices:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None:
        raise CatalogUnavailableError("Amazon Music services are not configured.")
    return services


def get_queue_service(request: Request) -> QueueService:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None or services.queue is None:
        raise QueueUnavailableError("The download queue is not configured.")
    return services.queue


def get_now_playing_service(request: Request) -> NowPlayingService:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None or services.now_playing is None:
        raise NowPlayingUnavailableError("Now Playing is not configured.")
    return services.now_playing


def get_library_service(request: Request) -> LibraryService:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None or services.library is None:
        raise LibraryUnavailableError("The library index is not configured.")
    return services.library


ServicesDependency = Annotated[ApplicationServices, Depends(get_services)]
QueueDependency = Annotated[QueueService, Depends(get_queue_service)]
NowPlayingDependency = Annotated[NowPlayingService, Depends(get_now_playing_service)]
LibraryDependency = Annotated[LibraryService, Depends(get_library_service)]
