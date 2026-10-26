from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from spotui.domain.spotify import (
    SpotifyEntityType,
    SpotifyExtractionError,
    SpotifyUrlError,
    parse_spotify_link,
)
from spotui.providers.spotify.embed import (
    SpotifyEmbedProvider,
    _SafeRedirectHandler,
    parse_embed_html,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PLAYLIST_ID = "1111111111111111111111"
ALBUM_ID = "3333333333333333333333"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def playlist_html() -> str:
    return fixture("spotify_playlist_embed.html")


def album_html() -> str:
    return fixture("spotify_album_embed.html")


@pytest.mark.parametrize(
    ("url", "kind", "spotify_id", "short"),
    [
        (
            f"https://open.spotify.com/playlist/{PLAYLIST_ID}?si=abc",
            SpotifyEntityType.PLAYLIST,
            PLAYLIST_ID,
            False,
        ),
        (
            f"https://open.spotify.com/intl-de/album/{ALBUM_ID}",
            SpotifyEntityType.ALBUM,
            ALBUM_ID,
            False,
        ),
        ("https://spotify.link/AbCdEf123", None, None, True),
        ("https://spotify.app.link/AbCdEf123", None, None, True),
    ],
)
def test_public_spotify_links_are_accepted(
    url: str,
    kind: SpotifyEntityType | None,
    spotify_id: str | None,
    short: bool,
) -> None:
    link = parse_spotify_link(url)

    assert link.kind is kind
    assert link.spotify_id == spotify_id
    assert link.is_short_link is short


@pytest.mark.parametrize(
    "url",
    [
        "http://open.spotify.com/playlist/1111111111111111111111",
        "https://example.com/playlist/1111111111111111111111",
        "https://open.spotify.com/track/1111111111111111111111",
        "https://open.spotify.com/artist/1111111111111111111111",
        "https://open.spotify.com/playlist/short",
        "https://user:pass@open.spotify.com/playlist/1111111111111111111111",
        "https://open.spotify.com:443/playlist/1111111111111111111111",
        "not-a-url",
    ],
)
def test_unsupported_spotify_links_are_rejected(url: str) -> None:
    with pytest.raises(SpotifyUrlError):
        parse_spotify_link(url)


def test_playlist_parser_preserves_order_duplicates_and_positions() -> None:
    collection = parse_embed_html(
        playlist_html(),
        expected_kind=SpotifyEntityType.PLAYLIST,
        expected_id=PLAYLIST_ID,
    )

    assert collection.kind is SpotifyEntityType.PLAYLIST
    assert collection.spotify_id == PLAYLIST_ID
    assert collection.title == "Road Trip"
    assert collection.artwork_url == "https://images.example/road-trip.jpg"
    assert [track.position for track in collection.tracks] == [0, 2, 3]
    assert [track.title for track in collection.tracks] == [
        "First Song",
        "Second Song",
        "First Song",
    ]
    assert collection.tracks[1].artist == "Artist Two, Guest"
    assert collection.tracks[0].duration_seconds == 180.0
    assert collection.tracks[0].spotify_track_id == "2222222222222222222221"
    assert (
        collection.tracks[0].source_url
        == "https://open.spotify.com/track/2222222222222222222221"
    )


def test_album_parser_accepts_missing_artwork() -> None:
    collection = parse_embed_html(
        album_html(),
        expected_kind=SpotifyEntityType.ALBUM,
        expected_id=ALBUM_ID,
    )

    assert collection.kind is SpotifyEntityType.ALBUM
    assert collection.title == "Short Album"
    assert collection.artwork_url is None
    assert len(collection.tracks) == 2


def test_parser_rejects_wrong_type_or_id_and_structural_changes() -> None:
    with pytest.raises(SpotifyExtractionError, match="different item type"):
        parse_embed_html(
            playlist_html(),
            expected_kind=SpotifyEntityType.ALBUM,
            expected_id=PLAYLIST_ID,
        )
    with pytest.raises(SpotifyExtractionError, match="different item"):
        parse_embed_html(
            playlist_html(),
            expected_kind=SpotifyEntityType.PLAYLIST,
            expected_id="9999999999999999999999",
        )
    with pytest.raises(SpotifyExtractionError, match="structure has changed"):
        parse_embed_html("<html><body>No data</body></html>")
    with pytest.raises(SpotifyExtractionError, match="invalid metadata"):
        parse_embed_html(
            '<script id="__NEXT_DATA__" type="application/json">{bad}</script>'
        )


def test_provider_fetches_the_public_embed_page() -> None:
    requested: list[str] = []

    def fetcher(url: str) -> tuple[str, str]:
        requested.append(url)
        return url, playlist_html()

    provider = SpotifyEmbedProvider(fetcher=fetcher)
    collection = provider.extract(
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
    )

    assert collection.title == "Road Trip"
    assert requested == [
        f"https://open.spotify.com/embed/playlist/{PLAYLIST_ID}"
    ]


def test_provider_resolves_short_link_then_fetches_embed() -> None:
    requested: list[str] = []
    final_url = f"https://open.spotify.com/playlist/{PLAYLIST_ID}?si=resolved"

    def fetcher(url: str) -> tuple[str, str]:
        requested.append(url)
        if url == "https://spotify.link/AbCdEf123":
            return final_url, "<html>redirect landing page</html>"
        return url, playlist_html()

    provider = SpotifyEmbedProvider(fetcher=fetcher)
    collection = provider.extract("https://spotify.link/AbCdEf123")

    assert collection.title == "Road Trip"
    assert requested[0] == "https://spotify.link/AbCdEf123"
    assert requested[1] == f"https://open.spotify.com/embed/playlist/{PLAYLIST_ID}"


def test_provider_rejects_short_link_that_does_not_resolve_to_public_item() -> None:
    provider = SpotifyEmbedProvider(
        fetcher=lambda _url: ("https://open.spotify.com/track/1111111111111111111111", "")
    )

    with pytest.raises(SpotifyExtractionError, match="did not resolve"):
        provider.extract("https://spotify.link/AbCdEf123")


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/playlist/1111111111111111111111",
        "http://open.spotify.com/playlist/1111111111111111111111",
        "https://user:pass@open.spotify.com/playlist/1111111111111111111111",
        "https://open.spotify.com:8443/playlist/1111111111111111111111",
    ],
)
def test_redirects_to_unsupported_targets_are_rejected(target: str) -> None:
    handler = _SafeRedirectHandler()
    request = urllib.request.Request(
        "https://spotify.link/AbCdEf123",
    )

    with pytest.raises(SpotifyExtractionError, match="unsupported address"):
        handler.redirect_request(request, None, 302, "Found", {}, target)
