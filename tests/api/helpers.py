from __future__ import annotations

from spotui.schemas.errors import ErrorCode


def assert_problem(response, status_code: int, code: ErrorCode) -> dict:
    assert response.status_code == status_code
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == f"urn:spotui:error:{code.value}"
    assert body["status"] == status_code
    assert body["code"] == code.value
    assert body["title"]
    assert body["detail"]
    assert body["instance"]
    assert body["request_id"] == response.headers["x-request-id"]
    return body
