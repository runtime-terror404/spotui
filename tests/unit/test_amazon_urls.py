from __future__ import annotations

import pytest

from spotui.domain.amazon import AmazonUrlError, parse_amazon_url
from spotui.domain.catalog import CatalogKind


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://music.amazon.in/artists/B006ZO8YNU/arijit-singh", CatalogKind.ARTIST),
        ("https://music.amazon.com/albums/B001ALBUM", CatalogKind.ALBUM),
        ("https://music.amazon.in/playlists/B003PLAYLIST", CatalogKind.PLAYLIST),
        ("https://music.amazon.in/user-playlists/B004COMMUNITY", CatalogKind.COMMUNITY_PLAYLIST),
        ("https://music.amazon.com/tracks/B002TRACK", CatalogKind.TRACK),
        (
            "https://music.amazon.in/albums/B001ALBUM?trackAsin=B002TRACK",
            CatalogKind.ALBUM,
        ),
    ],
)
def test_supported_urls_are_classified(url: str, kind: CatalogKind) -> None:
    parsed = parse_amazon_url(url)

    assert parsed.kind is kind
    assert parsed.original == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "http://music.amazon.in/albums/B001",
        "https://example.com/albums/B001",
        "https://music.amazon.com.evil.example/albums/B001",
        "https://user:pass@music.amazon.in/albums/B001",
        "https://music.amazon.in:443/albums/B001",
        "https://music.amazon.in/albums/",
        "https://music.amazon.in/stations/B001",
    ],
)
def test_unsupported_urls_are_rejected(url: str) -> None:
    with pytest.raises(AmazonUrlError):
        parse_amazon_url(url)


def test_host_matching_is_case_insensitive() -> None:
    parsed = parse_amazon_url("https://MUSIC.AMAZON.IN/albums/B001")

    assert parsed.host == "music.amazon.in"
