"""Shared API dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from spotui.domain.errors import (
    CatalogUnavailableError,
    QueueUnavailableError,
)
from spotui.services.container import ApplicationServices
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


ServicesDependency = Annotated[ApplicationServices, Depends(get_services)]
QueueDependency = Annotated[QueueService, Depends(get_queue_service)]
