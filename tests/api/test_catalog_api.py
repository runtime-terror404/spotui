from __future__ import annotations

import pytest

from spotui.app import create_app
from spotui.domain.errors import (
    CatalogResponseError,
    CatalogTimeoutError,
    CatalogUnavailableError,
)
from spotui.schemas.errors import ErrorCode
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.search import SearchService
from tests.api.helpers import CSRFTestClient as TestClient
from tests.api.helpers import assert_problem
from tests.fakes import FakeLibrary


def test_search_returns_grouped_results(catalog_client, fake_catalog) -> None:
    response = catalog_client.get("/api/v1/search", params={"q": "  Arijit   Singh "})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Arijit Singh"
    assert [section["title"] for section in body["sections"]] == [
        "Artists",
        "Albums",
        "Songs",
    ]
    assert [section["kind"] for section in body["sections"]] == [
        "artist",
        "album",
        "track",
    ]
    assert fake_catalog.search_calls == ["Arijit Singh"]
    assert "in_library" not in body["sections"][2]["items"][0]


def test_search_requires_a_query(catalog_client) -> None:
    response = catalog_client.get("/api/v1/search")

    body = assert_problem(response, 422, ErrorCode.VALIDATION_ERROR)
    assert body["errors"]


def test_whitespace_search_is_rejected(catalog_client) -> None:
    response = catalog_client.get("/api/v1/search", params={"q": "   "})

    body = assert_problem(response, 422, ErrorCode.VALIDATION_ERROR)
    assert body["title"] == "Invalid search query"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            CatalogUnavailableError("The Amazon Music browser is unavailable."),
            503,
            ErrorCode.AMAZON_UNAVAILABLE,
        ),
        (
            CatalogTimeoutError("Amazon Music search did not respond in time."),
            504,
            ErrorCode.AMAZON_TIMEOUT,
        ),
        (
            CatalogResponseError("Amazon Music search failed."),
            502,
            ErrorCode.AMAZON_SEARCH_FAILED,
        ),
    ],
)
def test_search_provider_errors_are_mapped(
    catalog_client, fake_catalog, error, status_code, code
) -> None:
    fake_catalog.search_error = error

    response = catalog_client.get("/api/v1/search", params={"q": "arijit"})

    body = assert_problem(response, status_code, code)
    assert body["detail"] == str(error)


def test_search_and_detail_expose_library_match_confidence(
    runtime,
    fake_catalog,
) -> None:
    library = FakeLibrary(in_library=True)
    runtime.services = ApplicationServices(
        search=SearchService(fake_catalog, library=library),
        entity_details=EntityDetailsService(fake_catalog, library=library),
        resources=(),
    )
    app = create_app(runtime, serve_frontend=False)

    with TestClient(app) as client:
        search = client.get("/api/v1/search", params={"q": "arijit"})
        detail = client.get(
            "/api/v1/entities/detail",
            params={"url": "https://music.amazon.in/albums/B001ALBUM"},
        )

    track = search.json()["sections"][2]["items"][0]
    assert track["in_library"] is True
    assert track["library_match"] == "likely"
    assert detail.json()["tracks"][0]["in_library"] is True
    assert detail.json()["tracks"][0]["library_match"] == "likely"


def test_detail_returns_typed_entity(catalog_client, fake_catalog) -> None:
    response = catalog_client.get(
        "/api/v1/entities/detail",
        params={"url": "https://music.amazon.in/albums/B001ALBUM"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "album"
    assert body["title"] == "Aashiqui 2"
    assert body["tracks"][0]["title"] == "Tum Hi Ho"
    assert body["albums"][0]["subtitle"] == "Album • 2013"
    assert "in_library" not in body["tracks"][0]
    assert fake_catalog.detail_calls[0].kind.value == "album"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/albums/B001",
        "http://music.amazon.in/albums/B001",
        "https://music.amazon.in/tracks/B001",
        "https://music.amazon.in/stations/B001",
    ],
)
def test_detail_rejects_unsupported_urls(catalog_client, fake_catalog, url: str) -> None:
    response = catalog_client.get("/api/v1/entities/detail", params={"url": url})

    assert_problem(response, 400, ErrorCode.INVALID_URL)
    assert fake_catalog.detail_calls == []


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            CatalogUnavailableError("The managed lucidadl environment is missing."),
            503,
            ErrorCode.AMAZON_UNAVAILABLE,
        ),
        (
            CatalogTimeoutError("Amazon catalog resolution timed out."),
            504,
            ErrorCode.AMAZON_TIMEOUT,
        ),
        (
            CatalogResponseError("No downloadable tracks were returned for this item."),
            502,
            ErrorCode.AMAZON_SEARCH_FAILED,
        ),
    ],
)
def test_detail_provider_errors_are_mapped(
    catalog_client, fake_catalog, error, status_code, code
) -> None:
    fake_catalog.detail_error = error

    response = catalog_client.get(
        "/api/v1/entities/detail",
        params={"url": "https://music.amazon.in/albums/B001ALBUM"},
    )

    body = assert_problem(response, status_code, code)
    assert body["detail"] == str(error)


def test_catalog_routes_are_unavailable_without_services(client) -> None:
    search = client.get("/api/v1/search", params={"q": "arijit"})
    detail = client.get(
        "/api/v1/entities/detail",
        params={"url": "https://music.amazon.in/albums/B001ALBUM"},
    )

    assert_problem(search, 503, ErrorCode.AMAZON_UNAVAILABLE)
    assert_problem(detail, 503, ErrorCode.AMAZON_UNAVAILABLE)


def test_detail_requires_url(catalog_client) -> None:
    response = catalog_client.get("/api/v1/entities/detail")

    body = assert_problem(response, 422, ErrorCode.VALIDATION_ERROR)
    assert body["errors"]
