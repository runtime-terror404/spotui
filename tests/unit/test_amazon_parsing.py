from __future__ import annotations

import json
from pathlib import Path

import pytest

from spotui.domain.catalog import CatalogKind
from spotui.domain.errors import CatalogResponseError
from spotui.providers.amazon.parsing import (
    parse_artist_payload,
    parse_community_playlist_rows,
    parse_lucida_info,
    parse_search_payload,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_search_payload_is_grouped_filtered_and_deduped() -> None:
    sections = parse_search_payload(load("amazon_search.json"))

    assert [section.title for section in sections] == [
        "Artists",
        "Albums",
        "Songs",
        "Playlists",
        "Community Playlists",
    ]
    artists, albums, songs, playlists, community = sections
    assert artists.kind is CatalogKind.ARTIST
    assert len(artists.items) == 1
    assert artists.items[0].url == "https://music.amazon.in/artists/B006ZO8YNU/arijit-singh"
    assert artists.items[0].image == "https://images.example/arijit.jpg"

    assert albums.kind is CatalogKind.ALBUM
    assert [item.title for item in albums.items] == ["Aashiqui 2"]

    assert songs.kind is CatalogKind.TRACK
    assert songs.items[0].kind is CatalogKind.TRACK
    assert songs.items[0].subtitle == "Arijit Singh"

    assert playlists.kind is CatalogKind.PLAYLIST
    assert community.kind is CatalogKind.COMMUNITY_PLAYLIST


def test_malformed_search_payload_is_reported() -> None:
    with pytest.raises(CatalogResponseError):
        parse_search_payload({"unexpected": True})


def test_empty_search_payload_returns_no_sections() -> None:
    assert parse_search_payload({"methods": [{"template": {"widgets": []}}]}) == ()


def test_artist_payload_parses_tracks_and_albums() -> None:
    detail = parse_artist_payload(
        load("amazon_artist.json"),
        "Arijit Singh on Amazon Prime Music",
    )

    assert detail.kind is CatalogKind.ARTIST
    assert detail.title == "Arijit Singh"
    assert len(detail.tracks) == 1
    assert detail.tracks[0].title == "Tum Hi Ho"
    assert detail.tracks[0].artist == "Arijit Singh"
    assert detail.tracks[0].url.endswith("?trackAsin=B002TRACK")
    assert len(detail.albums) == 1
    assert detail.albums[0].subtitle == "Album • 2013"
    assert detail.image == "https://images.example/tum.jpg"


def test_empty_artist_payload_is_reported() -> None:
    with pytest.raises(CatalogResponseError):
        parse_artist_payload({"methods": []}, "Artist")


def test_community_playlist_rows_keep_playlist_order_and_dedupe() -> None:
    rows = [
        {
            "key": "track-2",
            "title": "Second",
            "artist": "Artist B",
            "href": "/albums/B002?trackAsin=B002TRACK",
            "style": "top: 80px",
        },
        {
            "key": "track-1",
            "title": "First",
            "artist": "Artist A",
            "href": "/albums/B001?trackAsin=B001TRACK",
            "style": "top: 40px",
        },
        {
            "key": "track-1",
            "title": "First duplicate",
            "artist": "Artist A",
            "href": "/albums/B001?trackAsin=B001TRACK",
            "style": "top: 40px",
        },
    ]

    detail = parse_community_playlist_rows(rows, "My List | Amazon Music")

    assert detail.kind is CatalogKind.COMMUNITY_PLAYLIST
    assert detail.title == "My List"
    assert [track.title for track in detail.tracks] == ["First", "Second"]
    assert all(track.url.startswith("https://music.amazon.in/") for track in detail.tracks)


def test_empty_community_playlist_is_reported() -> None:
    with pytest.raises(CatalogResponseError):
        parse_community_playlist_rows([], "Playlist")


def test_lucida_raw_info_is_normalized() -> None:
    detail = parse_lucida_info(load("lucida_album.json"))

    assert detail.kind is CatalogKind.ALBUM
    assert detail.title == "Aashiqui 2"
    assert detail.subtitle == "Arijit Singh, Jeet Gannguli"
    assert detail.image == "https://images.example/aashiqui.jpg"
    assert [track.title for track in detail.tracks] == ["Tum Hi Ho", "Sunn Raha Hai"]
    assert detail.tracks[1].artist == "Ankit Tiwari"


def test_lucida_normalized_bridge_info_is_supported() -> None:
    detail = parse_lucida_info(
        {
            "type": "playlist",
            "title": "Evening",
            "artist": "Various Artists",
            "cover": "https://images.example/cover.jpg",
            "tracks": [
                {
                    "title": "Track",
                    "artist": "Singer",
                    "url": "https://music.amazon.com/tracks/B001",
                }
            ],
        }
    )

    assert detail.kind is CatalogKind.PLAYLIST
    assert detail.subtitle == "Various Artists"
    assert detail.tracks[0].artist == "Singer"


def test_lucida_info_without_tracks_or_type_is_rejected() -> None:
    with pytest.raises(CatalogResponseError):
        parse_lucida_info({"type": "track", "title": "x", "tracks": []})
    with pytest.raises(CatalogResponseError):
        parse_lucida_info({"type": "album", "title": "x", "tracks": []})
