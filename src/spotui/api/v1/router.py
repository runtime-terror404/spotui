from __future__ import annotations

from fastapi import APIRouter

from spotui.api.v1.routes import (
    entities,
    health,
    imports,
    library,
    now_playing,
    queue,
    search,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router, tags=["system"])
router.include_router(search.router, tags=["catalog"])
router.include_router(entities.router, tags=["catalog"])
router.include_router(queue.router, tags=["queue"])
router.include_router(now_playing.router, tags=["now-playing"])
router.include_router(library.router, tags=["library"])
router.include_router(imports.router, tags=["imports"])
