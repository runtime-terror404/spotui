from __future__ import annotations

import re

import spotui

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def test_health_contract(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["ok"] is True
    assert body["version"] == spotui.__version__
    assert body["uptime_seconds"] >= 0
    assert set(body) == {"ok", "version", "uptime_seconds"}


def test_request_id_is_generated_and_returned(client) -> None:
    response = client.get("/api/v1/health")

    request_id = response.headers["x-request-id"]
    assert REQUEST_ID_RE.fullmatch(request_id)
    assert len(request_id) == 32


def test_valid_request_id_is_echoed(client) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-1"})

    assert response.headers["x-request-id"] == "test-request-1"


def test_untrusted_request_id_is_replaced(client) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "bad\nvalue " + "x" * 100},
    )

    request_id = response.headers["x-request-id"]
    assert request_id != "bad\nvalue " + "x" * 100
    assert REQUEST_ID_RE.fullmatch(request_id)


def test_unknown_route_still_has_request_id(client) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert REQUEST_ID_RE.fullmatch(response.headers["x-request-id"])


def test_root_serves_packaged_placeholder(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "SpotUI" in response.text
    assert "/api/v1/health" in response.text


def test_placeholder_is_packaged() -> None:
    from importlib import resources

    resource = resources.files("spotui.web").joinpath("placeholder.html")

    assert resource.is_file()


def test_openapi_exposes_only_versioned_health_route(client) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/health" in schema["paths"]
    assert "/api/health" not in schema["paths"]
