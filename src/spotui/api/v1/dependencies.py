"""Shared API dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from spotui.domain.errors import CatalogUnavailableError
from spotui.services.container import ApplicationServices


def get_services(request: Request) -> ApplicationServices:
    services = getattr(request.app.state.runtime, "services", None)
    if services is None:
        raise CatalogUnavailableError("Amazon Music services are not configured.")
    return services


ServicesDependency = Annotated[ApplicationServices, Depends(get_services)]
