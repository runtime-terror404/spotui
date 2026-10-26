"""RFC 9457 Problem Details contracts and stable SpotUI error codes."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(StrEnum):
    """Stable machine-readable error identifiers.

    New codes may be added, but an existing code must not be repurposed
    without an API compatibility decision.
    """

    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    HTTP_ERROR = "http_error"

    INVALID_URL = "invalid_url"
    SPOTIFY_EXTRACTION_FAILED = "spotify_extraction_failed"
    AMAZON_SEARCH_FAILED = "amazon_search_failed"
    ACTIVE_IMPORT_CONFLICT = "active_import_conflict"
    INVALID_SELECTION = "invalid_selection"
    STALE_REVISION = "stale_revision"
    DUPLICATE_ACTIVE_JOB = "duplicate_active_job"
    JOB_NOT_FOUND = "job_not_found"
    INVALID_TRANSITION = "invalid_transition"
    DOWNLOADER_UNAVAILABLE = "downloader_unavailable"
    INVALID_LIBRARY_ROOT = "invalid_library_root"
    INVALID_CONFIGURATION = "invalid_configuration"
    PORT_UNAVAILABLE = "port_unavailable"
    DEVICE_UNAUTHENTICATED = "device_unauthenticated"
    PAIRING_FAILED = "pairing_failed"
    INVALID_HOST_ORIGIN = "invalid_host_origin"
    CSRF_FAILED = "csrf_failed"
    INTERNAL_ERROR = "internal_error"


class FieldIssue(BaseModel):
    """A safe validation issue without echoing the submitted value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location: str
    message: str


class ProblemDetails(BaseModel):
    """RFC 9457 body plus SpotUI extensions.

    ``type`` is a stable URN, ``code`` is the stable SpotUI identifier, and
    ``request_id`` correlates the response with redacted server logs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    instance: str | None = None
    code: ErrorCode
    request_id: str
    errors: list[FieldIssue] | None = None
