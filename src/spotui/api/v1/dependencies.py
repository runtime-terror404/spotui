"""Shared API dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from spotui.api.v1.errors import ApiError
from spotui.domain.errors import (
    CatalogUnavailableError,
    ImportsUnavailableError,
    LibraryUnavailableError,
    NowPlayingUnavailableError,
    PairingUnavailableError,
    QueueUnavailableError,
)
from spotui.schemas.errors import ErrorCode
from spotui.services.container import ApplicationServices
from spotui.services.imports import ImportService
from spotui.services.library import LibraryService
from spotui.services.now_playing import NowPlayingService
from spotui.services.queue import QueueService
from spotui.services.system_info import SystemInfoService
from spotui.services.trusted_devices import TrustedDeviceService


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


def get_import_service(request: Request) -> ImportService:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None or services.imports is None:
        raise ImportsUnavailableError("Spotify imports are not configured.")
    return services.imports


def get_trusted_device_service(request: Request) -> TrustedDeviceService:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None or services.trusted_devices is None:
        raise PairingUnavailableError("Trusted-device pairing is not configured.")
    return services.trusted_devices


def get_system_info_service(request: Request) -> SystemInfoService:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None or services.system_info is None:
        raise ApiError(
            status_code=503,
            code=ErrorCode.SYSTEM_UNAVAILABLE,
            title="System information unavailable",
            detail="Application information is not configured.",
        )
    return services.system_info


def require_local_access(request: Request) -> None:
    if not getattr(request.state, "spotui_local", False):
        raise ApiError(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            title="Local access required",
            detail="Device pairing and management are available from the desktop host.",
        )


ServicesDependency = Annotated[ApplicationServices, Depends(get_services)]
QueueDependency = Annotated[QueueService, Depends(get_queue_service)]
NowPlayingDependency = Annotated[NowPlayingService, Depends(get_now_playing_service)]
LibraryDependency = Annotated[LibraryService, Depends(get_library_service)]
ImportDependency = Annotated[ImportService, Depends(get_import_service)]
SystemInfoDependency = Annotated[
    SystemInfoService,
    Depends(get_system_info_service),
]
TrustedDeviceDependency = Annotated[
    TrustedDeviceService,
    Depends(get_trusted_device_service),
]
LocalAccessDependency = Annotated[None, Depends(require_local_access)]
