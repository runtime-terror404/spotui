from __future__ import annotations

import logging

import pytest

from spotui.app import create_app
from spotui.persistence.migrate import SchemaNotCurrentError
from spotui.runtime import ApplicationRuntime
from spotui.server import Listener
from tests.api.helpers import CSRFTestClient as TestClient


def test_startup_requires_current_migrations(env, database_url: str) -> None:
    env.paths.ensure_runtime_directories()
    runtime = ApplicationRuntime(
        config=env.config,
        paths=env.paths,
        listeners=(Listener(kind="local", host="127.0.0.1", port=8765),),
    )
    app = create_app(runtime)

    with pytest.raises(SchemaNotCurrentError, match="spotui db upgrade"):
        with TestClient(app):
            pass

    assert runtime.database is None


def test_lifespan_initializes_and_disposes_database(
    app, runtime: ApplicationRuntime, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="spotui.app"), TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert runtime.database is not None
        assert runtime.started_at > 0
        assert runtime.stopping is False

    assert runtime.database is None
    assert runtime.stopping is True
    messages = [record.message for record in caplog.records]
    assert any("starting" in message for message in messages)
    assert any("stopped" in message for message in messages)


def test_listeners_are_logged(
    app, runtime: ApplicationRuntime, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="spotui.app"), TestClient(app):
        pass

    assert any("http://127.0.0.1:8765" in record.message for record in caplog.records)


def test_lifespan_is_reentrant_after_clean_shutdown(app, runtime: ApplicationRuntime) -> None:
    with TestClient(app):
        assert runtime.database is not None
    with TestClient(app):
        assert runtime.database is not None
    assert runtime.database is None


def test_custom_placeholder(app, runtime: ApplicationRuntime) -> None:
    custom = create_app(
        runtime,
        placeholder_html="<html>custom shell</html>",
        serve_frontend=False,
    )

    with TestClient(custom) as client:
        assert client.get("/").text == "<html>custom shell</html>"
