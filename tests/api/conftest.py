from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spotui.app import create_app
from spotui.runtime import ApplicationRuntime
from spotui.server import Listener
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.search import SearchService
from tests.fakes import FakeCatalog


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
    return create_app(runtime, serve_frontend=False)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture
def services(fake_catalog: FakeCatalog) -> ApplicationServices:
    return ApplicationServices(
        search=SearchService(fake_catalog),
        entity_details=EntityDetailsService(fake_catalog),
        resources=(),
    )


@pytest.fixture
def catalog_app(runtime: ApplicationRuntime, services: ApplicationServices) -> FastAPI:
    runtime.services = services
    return create_app(runtime, serve_frontend=False)


@pytest.fixture
def catalog_client(catalog_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(catalog_app) as test_client:
        yield test_client
