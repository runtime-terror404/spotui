from __future__ import annotations

from fastapi.testclient import TestClient

from spotui.schemas.errors import ErrorCode
from spotui.security.cookies import CSRF_COOKIE_NAME


class CSRFTestClient(TestClient):
    """Test client that primes the double-submit cookie on context entry."""

    def __enter__(self):
        client = super().__enter__()
        super().get("/api/v1/health")
        token = self.cookies.get(CSRF_COOKIE_NAME)
        if token:
            self.headers["X-CSRF-Token"] = token
        return client


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
