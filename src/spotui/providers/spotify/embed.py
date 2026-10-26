"""Public Spotify embed-page extraction; no login or OAuth is used."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

from spotui.domain.spotify import (
    ALLOWED_SPOTIFY_HOSTS,
    SpotifyCollection,
    SpotifyEntityType,
    SpotifyExtractionError,
    SpotifyTimeoutError,
    SpotifyTrackOccurrence,
    SpotifyUrlError,
    parse_spotify_link,
    spotify_track_url,
)

DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 4
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_SPOTIFY_TRACK_URI_RE = re.compile(r"^spotify:track:([A-Za-z0-9]{22})$")
_SPOTIFY_ENTITY_TYPES = frozenset(kind.value for kind in SpotifyEntityType)

Fetcher = Callable[[str], tuple[str, str]]


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self) -> None:
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirects += 1
        if self.redirects > MAX_REDIRECTS:
            raise SpotifyExtractionError("The Spotify link redirected too many times.")
        target = urljoin(req.full_url, newurl)
        parsed = urlsplit(target)
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() not in ALLOWED_SPOTIFY_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise SpotifyExtractionError(
                "The Spotify link redirected to an unsupported address."
            )
        return super().redirect_request(req, fp, code, msg, headers, target)


def _fetch_page(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[str, str]:
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except SpotifyExtractionError:
        raise
    except TimeoutError as exc:
        raise SpotifyTimeoutError("Spotify did not respond in time.") from exc
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise SpotifyExtractionError(
                "The Spotify link could not be read. It may be private or unavailable."
            ) from exc
        raise SpotifyExtractionError(
            "Spotify returned an unexpected response."
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise SpotifyTimeoutError("Spotify did not respond in time.") from exc
        raise SpotifyExtractionError("Spotify could not be reached.") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise SpotifyExtractionError("The Spotify page was too large to process.")
    return final_url, body.decode("utf-8", errors="replace")


def _find_entity(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        entity_type = value.get("type")
        if (
            entity_type in _SPOTIFY_ENTITY_TYPES
            and ("trackList" in value or "name" in value or "title" in value)
        ):
            return value
        for child in value.values():
            found = _find_entity(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_entity(child)
            if found is not None:
                return found
    return None


def _entity_artwork(entity: dict[str, Any]) -> str | None:
    cover = entity.get("coverArt")
    if isinstance(cover, dict):
        sources = cover.get("sources")
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict):
                    url = source.get("url")
                    if isinstance(url, str) and url.strip():
                        return url.strip()
    for key in ("artworkUrl", "image", "imageUrl"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _duration_seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return float(value) / 1000.0


def parse_embed_html(
    html: str,
    *,
    expected_kind: SpotifyEntityType | None = None,
    expected_id: str | None = None,
) -> SpotifyCollection:
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        raise SpotifyExtractionError(
            "The Spotify page structure has changed or the link is not public."
        )
    try:
        data = json.loads(match.group(1))
    except (TypeError, ValueError) as exc:
        raise SpotifyExtractionError("The Spotify page contained invalid metadata.") from exc

    entity = _find_entity(data)
    if entity is None:
        raise SpotifyExtractionError(
            "No public album or playlist metadata was found on Spotify."
        )
    entity_type = SpotifyEntityType(entity["type"])
    if expected_kind is not None and entity_type is not expected_kind:
        raise SpotifyExtractionError("Spotify returned a different item type.")
    entity_id = entity.get("id") or entity.get("uri", "").rsplit(":", 1)[-1]
    if expected_id is not None and entity_id and entity_id != expected_id:
        raise SpotifyExtractionError("Spotify returned a different item than requested.")

    title = entity.get("name") or entity.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SpotifyExtractionError("The Spotify item has no title.")

    track_list = entity.get("trackList")
    if not isinstance(track_list, list):
        raise SpotifyExtractionError("The Spotify item did not contain a track list.")

    tracks: list[SpotifyTrackOccurrence] = []
    for position, item in enumerate(track_list):
        if not isinstance(item, dict):
            continue
        uri = item.get("uri")
        if not isinstance(uri, str):
            continue
        uri_match = _SPOTIFY_TRACK_URI_RE.match(uri)
        if uri_match is None:
            continue
        track_title = item.get("title")
        if not isinstance(track_title, str) or not track_title.strip():
            continue
        artist = item.get("subtitle")
        artist_text = (
            " ".join(artist.replace("\xa0", " ").split())
            if isinstance(artist, str)
            else ""
        )
        spotify_id = uri_match.group(1)
        tracks.append(
            SpotifyTrackOccurrence(
                position=position,
                spotify_track_id=spotify_id,
                source_url=spotify_track_url(spotify_id),
                title=track_title.strip(),
                artist=artist_text,
                duration_seconds=_duration_seconds(item.get("duration")),
            )
        )
    if not tracks:
        raise SpotifyExtractionError("The Spotify item did not contain any playable tracks.")

    return SpotifyCollection(
        kind=entity_type,
        spotify_id=str(entity_id),
        title=title.strip(),
        artwork_url=_entity_artwork(entity),
        tracks=tuple(tracks),
    )


class SpotifyEmbedProvider:
    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        fetcher: Fetcher | None = None,
    ) -> None:
        self._timeout = timeout
        self._fetcher = fetcher

    def extract(self, url: str) -> SpotifyCollection:
        link = parse_spotify_link(url)
        if link.is_short_link:
            final_url, _body = self._fetch(link.original)
            try:
                resolved = parse_spotify_link(final_url)
            except SpotifyUrlError as exc:
                raise SpotifyExtractionError(
                    "The Spotify short link did not resolve to an album or playlist."
                ) from exc
            if resolved.is_short_link:
                raise SpotifyExtractionError(
                    "The Spotify short link did not resolve to an album or playlist."
                )
            link = resolved
        assert link.kind is not None and link.spotify_id is not None
        embed_url = (
            f"https://open.spotify.com/embed/{link.kind.value}/{link.spotify_id}"
        )
        _final_url, html = self._fetch(embed_url)
        return parse_embed_html(
            html,
            expected_kind=link.kind,
            expected_id=link.spotify_id,
        )

    def _fetch(self, url: str) -> tuple[str, str]:
        if self._fetcher is not None:
            return self._fetcher(url)
        return _fetch_page(url, timeout=self._timeout)
