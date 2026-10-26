"""Application-owned Spotify import types and strict public-URL parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

ALLOWED_SPOTIFY_HOSTS = frozenset(
    {"open.spotify.com", "spotify.link", "spotify.app.link"}
)
_SPOTIFY_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
_PUBLIC_PATH_RE = re.compile(
    r"^/(?:intl-[a-z]{2}(?:-[A-Z]{2})?/)?(album|playlist)/([A-Za-z0-9]{22})(?:/|$)"
)
_SHORT_PATH_RE = re.compile(r"^/[A-Za-z0-9._-]+")


class SpotifyUrlError(ValueError):
    """The supplied value is not a supported public Spotify link."""


class SpotifyExtractionError(RuntimeError):
    """The public Spotify page could not be read or parsed."""


class SpotifyTimeoutError(SpotifyExtractionError):
    """The public Spotify page did not respond within the request window."""


class SpotifyEntityType(StrEnum):
    ALBUM = "album"
    PLAYLIST = "playlist"


@dataclass(frozen=True, slots=True)
class SpotifyLink:
    original: str
    kind: SpotifyEntityType | None
    spotify_id: str | None
    is_short_link: bool


@dataclass(frozen=True, slots=True)
class SpotifyTrackOccurrence:
    position: int
    spotify_track_id: str | None
    source_url: str | None
    title: str
    artist: str
    duration_seconds: float | None


@dataclass(frozen=True, slots=True)
class SpotifyCollection:
    kind: SpotifyEntityType
    spotify_id: str
    title: str
    artwork_url: str | None
    tracks: tuple[SpotifyTrackOccurrence, ...]


def _url_parts(raw_url: str):
    candidate = raw_url.strip() if isinstance(raw_url, str) else ""
    if not candidate:
        raise SpotifyUrlError("A public Spotify album or playlist URL is required.")
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise SpotifyUrlError("The Spotify URL is not valid.") from exc
    if parsed.scheme != "https":
        raise SpotifyUrlError("Spotify URLs must use https.")
    if parsed.username or parsed.password or parsed.port is not None:
        raise SpotifyUrlError("Spotify URLs must not include credentials or a port.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_SPOTIFY_HOSTS:
        raise SpotifyUrlError(
            "Only open.spotify.com album/playlist links and spotify.link short links "
            "are supported."
        )
    return candidate, parsed, host


def parse_spotify_link(raw_url: str) -> SpotifyLink:
    candidate, parsed, host = _url_parts(raw_url)
    if host in {"spotify.link", "spotify.app.link"}:
        if not _SHORT_PATH_RE.match(parsed.path):
            raise SpotifyUrlError("This Spotify short link is not valid.")
        return SpotifyLink(candidate, None, None, True)
    match = _PUBLIC_PATH_RE.match(parsed.path)
    if match is None:
        raise SpotifyUrlError("Only public Spotify album and playlist links are supported.")
    return SpotifyLink(
        original=candidate,
        kind=SpotifyEntityType(match.group(1)),
        spotify_id=match.group(2),
        is_short_link=False,
    )


def spotify_track_url(spotify_track_id: str | None) -> str | None:
    if not spotify_track_id or not _SPOTIFY_ID_RE.fullmatch(spotify_track_id):
        return None
    return f"https://open.spotify.com/track/{spotify_track_id}"
