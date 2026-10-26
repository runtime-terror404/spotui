"""RFC 9457 Problem Details handling for the application API."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from spotui.api.middleware import get_request_id
from spotui.domain.amazon import AmazonUrlError
from spotui.domain.errors import (
    ActiveImportConflictError,
    CatalogError,
    CatalogResponseError,
    CatalogTimeoutError,
    CatalogUnavailableError,
    DownloaderUnavailableError,
    DuplicateActiveJobError,
    ImportNotFoundError,
    ImportStateError,
    ImportsUnavailableError,
    InvalidSearchQueryError,
    InvalidSelectionError,
    JobNotFoundError,
    JobTransitionError,
    LibraryUnavailableError,
    NowPlayingUnavailableError,
    QueueUnavailableError,
)
from spotui.domain.spotify import (
    SpotifyExtractionError,
    SpotifyTimeoutError,
    SpotifyUrlError,
)
from spotui.logging_setup import log_context
from spotui.schemas.errors import ErrorCode, FieldIssue, ProblemDetails

logger = logging.getLogger("spotui.errors")

PROBLEM_MEDIA_TYPE = "application/problem+json"

_HTTP_EXCEPTION_CODES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class ApiError(Exception):
    """An expected API failure with a stable code and safe public message."""

    def __init__(
        self,
        *,
        status_code: int,
        code: ErrorCode,
        title: str,
        detail: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not 400 <= status_code <= 599:
            raise ValueError(f"invalid API error status {status_code}")
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail
        self.headers = dict(headers or {})
        super().__init__(detail)


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    title: str,
    detail: str,
    errors: list[FieldIssue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response with stable extensions."""
    request_id = get_request_id(request)
    body = ProblemDetails(
        type=f"urn:spotui:error:{code.value}",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=code,
        request_id=request_id,
        errors=errors,
    )
    response_headers = {"X-Request-ID": request_id, **dict(headers or {})}
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=response_headers,
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    if exc.status_code >= 500:
        with log_context(request_id=get_request_id(request)):
            logger.error(
                "api error %s on %s %s: %s",
                exc.status_code,
                request.method,
                request.url.path,
                exc.detail,
            )
    return problem_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=exc.headers,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    issues = []
    for error in exc.errors()[:20]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "request"
        issues.append(FieldIssue(location=location, message=str(error.get("msg", "Invalid value"))))
    return problem_response(
        request,
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        title="Request validation failed",
        detail="One or more request fields are invalid.",
        errors=issues,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    status_code = exc.status_code
    if not 400 <= status_code <= 599:
        logger.error(
            "HTTPException raised with non-error status %s on %s %s",
            status_code,
            request.method,
            request.url.path,
        )
        status_code = 500
        code = ErrorCode.INTERNAL_ERROR
        title = "Internal server error"
        detail = "An unexpected error occurred."
    else:
        code = _HTTP_EXCEPTION_CODES.get(status_code, ErrorCode.HTTP_ERROR)
        try:
            title = HTTPStatus(status_code).phrase
        except ValueError:
            title = "Request failed"
        detail = exc.detail.strip() if isinstance(exc.detail, str) else ""
        detail = detail or title
    return problem_response(
        request,
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        headers=exc.headers,
    )


def _catalog_failure(
    request: Request,
    exc: CatalogError,
    *,
    status_code: int,
    code: ErrorCode,
    title: str,
) -> JSONResponse:
    with log_context(request_id=get_request_id(request)):
        logger.warning("%s: %s", title, exc)
    return problem_response(
        request,
        status_code=status_code,
        code=code,
        title=title,
        detail=str(exc) or title,
    )


async def amazon_url_error_handler(request: Request, exc: AmazonUrlError) -> JSONResponse:
    return problem_response(
        request,
        status_code=400,
        code=ErrorCode.INVALID_URL,
        title="Invalid Amazon Music URL",
        detail=str(exc),
    )


async def invalid_search_query_handler(
    request: Request, exc: InvalidSearchQueryError
) -> JSONResponse:
    return problem_response(
        request,
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        title="Invalid search query",
        detail=str(exc),
    )


async def catalog_unavailable_handler(
    request: Request, exc: CatalogUnavailableError
) -> JSONResponse:
    return _catalog_failure(
        request,
        exc,
        status_code=503,
        code=ErrorCode.AMAZON_UNAVAILABLE,
        title="Amazon Music unavailable",
    )


async def catalog_timeout_handler(
    request: Request, exc: CatalogTimeoutError
) -> JSONResponse:
    return _catalog_failure(
        request,
        exc,
        status_code=504,
        code=ErrorCode.AMAZON_TIMEOUT,
        title="Amazon Music timed out",
    )


async def catalog_response_handler(
    request: Request, exc: CatalogResponseError
) -> JSONResponse:
    return _catalog_failure(
        request,
        exc,
        status_code=502,
        code=ErrorCode.AMAZON_SEARCH_FAILED,
        title="Amazon Music request failed",
    )


async def catalog_error_handler(request: Request, exc: CatalogError) -> JSONResponse:
    return _catalog_failure(
        request,
        exc,
        status_code=502,
        code=ErrorCode.AMAZON_SEARCH_FAILED,
        title="Amazon Music request failed",
    )


def _service_failure(
    request: Request,
    exc: Exception,
    *,
    status_code: int,
    code: ErrorCode,
    title: str,
) -> JSONResponse:
    with log_context(request_id=get_request_id(request)):
        logger.warning("%s: %s", title, exc)
    return problem_response(
        request,
        status_code=status_code,
        code=code,
        title=title,
        detail=str(exc) or title,
    )


async def job_not_found_handler(request: Request, exc: JobNotFoundError) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=404,
        code=ErrorCode.JOB_NOT_FOUND,
        title="Download job not found",
    )


async def job_transition_handler(
    request: Request, exc: JobTransitionError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=409,
        code=ErrorCode.INVALID_TRANSITION,
        title="Invalid queue action",
    )


async def duplicate_active_job_handler(
    request: Request, exc: DuplicateActiveJobError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=409,
        code=ErrorCode.DUPLICATE_ACTIVE_JOB,
        title="Track already queued",
    )


async def downloader_unavailable_handler(
    request: Request, exc: DownloaderUnavailableError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=503,
        code=ErrorCode.DOWNLOADER_UNAVAILABLE,
        title="Downloader unavailable",
    )


async def queue_unavailable_handler(
    request: Request, exc: QueueUnavailableError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=503,
        code=ErrorCode.DOWNLOADER_UNAVAILABLE,
        title="Download queue unavailable",
    )


async def now_playing_unavailable_handler(
    request: Request, exc: NowPlayingUnavailableError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=503,
        code=ErrorCode.NOW_PLAYING_UNAVAILABLE,
        title="Now Playing unavailable",
    )


async def library_unavailable_handler(
    request: Request, exc: LibraryUnavailableError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=503,
        code=ErrorCode.LIBRARY_UNAVAILABLE,
        title="Library index unavailable",
    )


async def spotify_url_error_handler(
    request: Request, exc: SpotifyUrlError
) -> JSONResponse:
    return problem_response(
        request,
        status_code=400,
        code=ErrorCode.INVALID_URL,
        title="Invalid Spotify URL",
        detail=str(exc),
    )


async def spotify_timeout_handler(
    request: Request, exc: SpotifyTimeoutError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=504,
        code=ErrorCode.SPOTIFY_EXTRACTION_FAILED,
        title="Spotify timed out",
    )


async def spotify_extraction_handler(
    request: Request, exc: SpotifyExtractionError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=502,
        code=ErrorCode.SPOTIFY_EXTRACTION_FAILED,
        title="Spotify import failed",
    )


async def imports_unavailable_handler(
    request: Request, exc: ImportsUnavailableError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=503,
        code=ErrorCode.IMPORTS_UNAVAILABLE,
        title="Spotify imports unavailable",
    )


async def import_not_found_handler(
    request: Request, exc: ImportNotFoundError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=404,
        code=ErrorCode.IMPORT_NOT_FOUND,
        title="Import not found",
    )


async def active_import_conflict_handler(
    request: Request, exc: ActiveImportConflictError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=409,
        code=ErrorCode.ACTIVE_IMPORT_CONFLICT,
        title="Import already active",
    )


async def import_state_handler(
    request: Request, exc: ImportStateError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=409,
        code=ErrorCode.INVALID_TRANSITION,
        title="Invalid import action",
    )


async def invalid_selection_handler(
    request: Request, exc: InvalidSelectionError
) -> JSONResponse:
    return _service_failure(
        request,
        exc,
        status_code=409,
        code=ErrorCode.INVALID_SELECTION,
        title="Invalid selection",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id(request)
    with log_context(request_id=request_id):
        logger.error(
            "unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    return problem_response(
        request,
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        title="Internal server error",
        detail="An unexpected error occurred.",
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the API error contract on an application."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(AmazonUrlError, amazon_url_error_handler)
    app.add_exception_handler(InvalidSearchQueryError, invalid_search_query_handler)
    app.add_exception_handler(CatalogUnavailableError, catalog_unavailable_handler)
    app.add_exception_handler(CatalogTimeoutError, catalog_timeout_handler)
    app.add_exception_handler(CatalogResponseError, catalog_response_handler)
    app.add_exception_handler(CatalogError, catalog_error_handler)
    app.add_exception_handler(JobNotFoundError, job_not_found_handler)
    app.add_exception_handler(JobTransitionError, job_transition_handler)
    app.add_exception_handler(DuplicateActiveJobError, duplicate_active_job_handler)
    app.add_exception_handler(DownloaderUnavailableError, downloader_unavailable_handler)
    app.add_exception_handler(QueueUnavailableError, queue_unavailable_handler)
    app.add_exception_handler(NowPlayingUnavailableError, now_playing_unavailable_handler)
    app.add_exception_handler(LibraryUnavailableError, library_unavailable_handler)
    app.add_exception_handler(SpotifyUrlError, spotify_url_error_handler)
    app.add_exception_handler(SpotifyTimeoutError, spotify_timeout_handler)
    app.add_exception_handler(SpotifyExtractionError, spotify_extraction_handler)
    app.add_exception_handler(ImportsUnavailableError, imports_unavailable_handler)
    app.add_exception_handler(ImportNotFoundError, import_not_found_handler)
    app.add_exception_handler(ActiveImportConflictError, active_import_conflict_handler)
    app.add_exception_handler(ImportStateError, import_state_handler)
    app.add_exception_handler(InvalidSelectionError, invalid_selection_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
