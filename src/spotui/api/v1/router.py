from __future__ import annotations

from fastapi import APIRouter

from spotui.api.v1.routes import entities, health, queue, search

router = APIRouter(prefix="/api/v1")
router.include_router(health.router, tags=["system"])
router.include_router(search.router, tags=["catalog"])
router.include_router(entities.router, tags=["catalog"])
router.include_router(queue.router, tags=["queue"])
