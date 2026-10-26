from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from spotui.app import create_app
from spotui.providers.mpris.base import NowPlayingStatus, NowPlayingTrack
from spotui.runtime import ApplicationRuntime
from spotui.schemas.errors import ErrorCode
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.now_playing import NowPlayingService
from spotui.services.search import SearchService
from tests.api.helpers import CSRFTestClient as TestClient
from tests.api.helpers import assert_problem
from tests.fakes import FakeCatalog


class FakeMpris:
    def __init__(self, status: NowPlayingStatus) -> None:
        self.status = status
        self.calls = 0

    def now_playing(self) -> NowPlayingStatus:
        self.calls += 1
        return self.status


@dataclass
class NowPlayingContext:
    client: TestClient
    provider: FakeMpris


@pytest.fixture
def now_playing_context(
    runtime: ApplicationRuntime,
    fake_catalog: FakeCatalog,
) -> Iterator[NowPlayingContext]:
    provider = FakeMpris(NowPlayingStatus(True, None, None, "No media player is running."))
    runtime.services = ApplicationServices(
        search=SearchService(fake_catalog),
        entity_details=EntityDetailsService(fake_catalog),
        now_playing=NowPlayingService(provider),
        resources=(),
    )
    app = create_app(runtime, serve_frontend=False)
    with TestClient(app) as client:
        yield NowPlayingContext(client=client, provider=provider)


def test_track_response(now_playing_context: NowPlayingContext) -> None:
    now_playing_context.provider.status = NowPlayingStatus(
        True,
        NowPlayingTrack("Tum Hi Ho", "Arijit Singh", "spotify:track:abc"),
        "spotifast",
        None,
    )

    response = now_playing_context.client.get("/api/v1/now-playing")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "available": True,
        "track": {
            "title": "Tum Hi Ho",
            "artist": "Arijit Singh",
            "track_id": "spotify:track:abc",
        },
        "player": "spotifast",
    }
    assert now_playing_context.provider.calls == 1


def test_no_track_reason_is_returned(now_playing_context: NowPlayingContext) -> None:
    response = now_playing_context.client.get("/api/v1/now-playing")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "reason": "No media player is running.",
    }


def test_missing_playerctl_is_not_an_http_error(
    now_playing_context: NowPlayingContext,
) -> None:
    now_playing_context.provider.status = NowPlayingStatus(
        False,
        None,
        None,
        "playerctl is not installed.",
    )

    response = now_playing_context.client.get("/api/v1/now-playing")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["reason"] == "playerctl is not installed."


def test_now_playing_requires_service(client) -> None:
    response = client.get("/api/v1/now-playing")

    assert_problem(response, 503, ErrorCode.NOW_PLAYING_UNAVAILABLE)
