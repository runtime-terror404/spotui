from __future__ import annotations

import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from spotui.api.v1.errors import ApiError
from spotui.logging_setup import setup_logging
from spotui.schemas.errors import ErrorCode
from tests.api.helpers import assert_problem


class CountBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int


def _build_test_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/_test", include_in_schema=False)

    @router.get("/api-error")
    def api_error() -> None:
        raise ApiError(
            status_code=409,
            code=ErrorCode.ACTIVE_IMPORT_CONFLICT,
            title="Import in progress",
            detail="Finish the active import first.",
            headers={"Retry-After": "5"},
        )

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("Authorization: Bearer topsecret")

    @router.post("/validate")
    def validate(body: CountBody) -> dict[str, int]:
        return {"count": body.count}

    @router.get("/non-error-http-exception")
    def non_error_http_exception() -> None:
        raise StarletteHTTPException(status_code=307, headers={"Location": "/elsewhere"})

    return router


@pytest.fixture
def error_app(app):
    app.include_router(_build_test_router())
    return app


def test_unknown_route_returns_problem_details(client) -> None:
    response = client.get(
        "/api/v1/does-not-exist",
        headers={"X-Request-ID": "missing-route-1"},
    )

    body = assert_problem(response, 404, ErrorCode.NOT_FOUND)
    assert body["request_id"] == "missing-route-1"
    assert body["instance"] == "/api/v1/does-not-exist"
    assert "errors" not in body


def test_wrong_method_returns_problem_details(client) -> None:
    response = client.post("/api/v1/health")

    assert_problem(response, 405, ErrorCode.METHOD_NOT_ALLOWED)


def test_api_error_mapping(error_app) -> None:
    with TestClient(error_app) as client:
        response = client.get(
            "/api/v1/_test/api-error",
            headers={"X-Request-ID": "api-error-1"},
        )

    body = assert_problem(response, 409, ErrorCode.ACTIVE_IMPORT_CONFLICT)
    assert body["request_id"] == "api-error-1"
    assert body["detail"] == "Finish the active import first."
    assert response.headers["retry-after"] == "5"


def test_non_error_http_exception_is_not_returned_as_3xx(error_app) -> None:
    with TestClient(error_app) as client:
        response = client.get("/api/v1/_test/non-error-http-exception")

    body = assert_problem(response, 500, ErrorCode.INTERNAL_ERROR)
    assert body["detail"] == "An unexpected error occurred."


def test_validation_error_is_safe_and_structured(error_app) -> None:
    with TestClient(error_app) as client:
        response = client.post("/api/v1/_test/validate", json={"count": "not-a-number"})

    body = assert_problem(response, 422, ErrorCode.VALIDATION_ERROR)
    assert body["errors"][0]["location"] == "body.count"
    assert body["errors"][0]["message"]
    assert "not-a-number" not in response.text


def test_internal_error_is_safe_and_logged(env, error_app) -> None:
    setup_logging(env.config.logging, env.paths, console=False)

    with TestClient(error_app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/_test/boom",
            headers={"X-Request-ID": "internal-error-1"},
        )

    body = assert_problem(response, 500, ErrorCode.INTERNAL_ERROR)
    assert body["request_id"] == "internal-error-1"
    assert body["detail"] == "An unexpected error occurred."
    assert "topsecret" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text

    for handler in logging.getLogger().handlers:
        handler.flush()
    log_text = env.paths.log_file.read_text(encoding="utf-8")
    assert "unhandled exception" in log_text
    assert "request_id=internal-error-1" in log_text
    assert "topsecret" not in log_text
