from __future__ import annotations

import logging

from spotui.config import LoggingSettings
from spotui.logging_setup import setup_logging
from tests.api.helpers import CSRFTestClient as TestClient


def test_access_log_contains_request_id_and_status_at_debug(env, app) -> None:
    setup_logging(
        LoggingSettings(level="DEBUG"),
        env.paths,
        console=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "log-test-1"})
        assert response.status_code == 200

    for handler in logging.getLogger().handlers:
        handler.flush()
    contents = env.paths.log_file.read_text(encoding="utf-8")

    assert "request_id=log-test-1" in contents
    assert "DEBUG" in contents
    assert "GET /api/v1/health -> 200" in contents


def test_successful_requests_are_quiet_at_info(env, app) -> None:
    setup_logging(env.config.logging, env.paths, console=False)

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200

    for handler in logging.getLogger().handlers:
        handler.flush()
    contents = env.paths.log_file.read_text(encoding="utf-8")

    assert "GET /api/v1/health -> 200" not in contents
