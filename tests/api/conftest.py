from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spotui.app import create_app
from spotui.runtime import ApplicationRuntime
from spotui.server import Listener


@pytest.fixture
def runtime(env, migrated_database_url: str) -> ApplicationRuntime:
    env.paths.ensure_runtime_directories()
    return ApplicationRuntime(
        config=env.config,
        paths=env.paths,
        listeners=(Listener(kind="local", host="127.0.0.1", port=env.config.server.port),),
    )


@pytest.fixture
def app(runtime: ApplicationRuntime) -> FastAPI:
    return create_app(runtime)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
