from __future__ import annotations

from fastapi import APIRouter

from spotui.api.v1.routes import health

router = APIRouter(prefix="/api/v1")
router.include_router(health.router, tags=["system"])
