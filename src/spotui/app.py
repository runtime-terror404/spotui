"""FastAPI application factory and lifespan."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from spotui import __version__
from spotui.api.middleware import RequestContextMiddleware
from spotui.api.v1.errors import install_error_handlers
from spotui.api.v1.router import router as api_router
from spotui.persistence.database import Database, database_url_for_path
from spotui.persistence.migrate import check_database_current
from spotui.runtime import ApplicationRuntime
from spotui.security.middleware import SecurityMiddleware

logger = logging.getLogger("spotui.app")


def packaged_web_dist() -> Path:
    return Path(__file__).resolve().parent / "web" / "dist"


def load_placeholder_html() -> str:
    resource = resources.files("spotui.web").joinpath("placeholder.html")
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"packaged placeholder frontend is missing: {exc}") from exc


def _resolve_web_dist(web_dist: Path | None) -> Path | None:
    candidate = web_dist if web_dist is not None else packaged_web_dist()
    if not (candidate / "index.html").is_file():
        if web_dist is not None:
            missing = candidate / "index.html"
            raise RuntimeError(f"frontend build is incomplete: {missing} is missing")
        return None
    if not (candidate / "assets").is_dir():
        missing = candidate / "assets"
        raise RuntimeError(f"frontend build is incomplete: {missing} is missing")
    return candidate


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

    try:
        if runtime.services is None and runtime.services_factory is not None:
            runtime.services = runtime.services_factory(
                runtime.config,
                runtime.paths,
                database,
            )
        if runtime.services is not None:
            runtime.services.start()
    except Exception:
        if runtime.services is not None:
            runtime.services.close()
        database.dispose()
        runtime.database = None
        logger.exception("service startup failed")
        raise

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
        if runtime.services is not None:
            runtime.services.close()
        if runtime.database is not None:
            runtime.database.dispose()
            runtime.database = None
        logger.info("SpotUI stopped")


def create_app(
    runtime: ApplicationRuntime,
    *,
    placeholder_html: str | None = None,
    serve_frontend: bool = True,
    web_dist: Path | None = None,
) -> FastAPI:
    """Build the ASGI application around one shared runtime."""
    dist = _resolve_web_dist(web_dist) if serve_frontend else None
    app = FastAPI(
        title="SpotUI",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.add_middleware(SecurityMiddleware, runtime=runtime)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(api_router)

    if dist is not None:
        app.mount(
            "/assets",
            StaticFiles(directory=dist / "assets"),
            name="frontend-assets",
        )

        @app.get("/", include_in_schema=False)
        def frontend_index() -> FileResponse:
            return FileResponse(dist / "index.html", media_type="text/html")
    else:
        html = load_placeholder_html() if placeholder_html is None else placeholder_html

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def index() -> HTMLResponse:
            return HTMLResponse(html)

    return app
