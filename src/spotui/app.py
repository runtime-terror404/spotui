"""FastAPI application factory and lifespan."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import resources

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from spotui import __version__
from spotui.api.middleware import RequestContextMiddleware
from spotui.api.v1.errors import install_error_handlers
from spotui.api.v1.router import router as api_router
from spotui.persistence.database import Database, database_url_for_path
from spotui.persistence.migrate import check_database_current
from spotui.runtime import ApplicationRuntime

logger = logging.getLogger("spotui.app")


def load_placeholder_html() -> str:
    resource = resources.files("spotui.web").joinpath("placeholder.html")
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"packaged placeholder frontend is missing: {exc}") from exc


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime: ApplicationRuntime = app.state.runtime
    runtime.started_at = time.monotonic()
    runtime.stopping = False
    runtime.paths.ensure_runtime_directories()

    database = Database.from_path(runtime.paths.database_file)
    try:
        check_database_current(database_url_for_path(runtime.paths.database_file))
    except Exception as exc:
        database.dispose()
        logger.error("startup blocked: %s", exc)
        raise
    runtime.database = database

    urls = [listener.url for listener in runtime.listeners]
    logger.info(
        "SpotUI %s starting; listeners=%s database=%s",
        __version__,
        urls or ["none"],
        runtime.paths.database_file,
    )
    try:
        yield
    finally:
        runtime.stopping = True
        logger.info("SpotUI shutting down")
        if runtime.database is not None:
            runtime.database.dispose()
            runtime.database = None
        logger.info("SpotUI stopped")


def create_app(runtime: ApplicationRuntime, *, placeholder_html: str | None = None) -> FastAPI:
    """Build the ASGI application around one shared runtime."""
    html = load_placeholder_html() if placeholder_html is None else placeholder_html
    app = FastAPI(
        title="SpotUI",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(api_router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(html)

    return app
