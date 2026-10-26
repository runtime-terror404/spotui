from __future__ import annotations

import time

from fastapi import APIRouter, Request

from spotui import __version__
from spotui.runtime import ApplicationRuntime
from spotui.schemas.system import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def read_health(request: Request) -> HealthResponse:
    runtime: ApplicationRuntime = request.app.state.runtime
    uptime = time.monotonic() - runtime.started_at if runtime.started_at else 0.0
    return HealthResponse(
        ok=True,
        version=__version__,
        uptime_seconds=round(max(0.0, uptime), 3),
    )
