"""Strict validation and classification of Amazon Music URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from spotui.domain.catalog import CatalogKind

ALLOWED_AMAZON_HOSTS = frozenset({"music.amazon.com", "music.amazon.in"})
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
_TRACK_PATH_RE = re.compile(r"^/tracks/([A-Za-z0-9]{10})(?:/|$)")

_PATH_KINDS: tuple[tuple[re.Pattern[str], CatalogKind], ...] = (
    (re.compile(r"^/artists/[^/]+"), CatalogKind.ARTIST),
    (re.compile(r"^/albums/[^/]+"), CatalogKind.ALBUM),
    (re.compile(r"^/playlists/[^/]+"), CatalogKind.PLAYLIST),
    (re.compile(r"^/user-playlists/[^/]+"), CatalogKind.COMMUNITY_PLAYLIST),
    (re.compile(r"^/tracks/[^/]+"), CatalogKind.TRACK),
)


class AmazonUrlError(ValueError):
    """The supplied value is not a supported Amazon Music URL."""


@dataclass(frozen=True, slots=True)
class AmazonUrl:
    original: str
    host: str
    path: str
    kind: CatalogKind


@dataclass(frozen=True, slots=True)
class AmazonTrackUrl:
    original: str
    asin: str
    track_key: str
    canonical_url: str


def _validated_parts(raw_url: str):
    candidate = raw_url.strip() if isinstance(raw_url, str) else ""
    if not candidate:
        raise AmazonUrlError("An Amazon Music URL is required.")
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise AmazonUrlError("The Amazon Music URL is not valid.") from exc

    if parsed.scheme != "https":
        raise AmazonUrlError("Amazon Music URLs must use https.")
    if parsed.username or parsed.password or parsed.port is not None:
        raise AmazonUrlError("Amazon Music URLs must not include credentials or a port.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_AMAZON_HOSTS:
        raise AmazonUrlError(
            "Only Amazon Music URLs on music.amazon.com or music.amazon.in are supported."
        )
    return candidate, parsed, host


def parse_amazon_url(raw_url: str) -> AmazonUrl:
    """Validate scheme, credentials, host, and supported entity path."""
    candidate, parsed, host = _validated_parts(raw_url)
    kind = next(
        (candidate_kind for pattern, candidate_kind in _PATH_KINDS if pattern.match(parsed.path)),
        None,
    )
    if kind is None:
        raise AmazonUrlError("This Amazon Music URL does not identify a supported item.")
    return AmazonUrl(original=candidate, host=host, path=parsed.path, kind=kind)


def parse_amazon_track_url(raw_url: str) -> AmazonTrackUrl:
    """Extract a normalized ASIN identity from an album/track URL."""
    candidate, parsed, _host = _validated_parts(raw_url)

    query_asins = parse_qs(parsed.query, keep_blank_values=True).get("trackAsin", [])
    path_match = _TRACK_PATH_RE.match(parsed.path)
    allowed_path = parsed.path.startswith("/albums/") or path_match is not None
    if not allowed_path:
        raise AmazonUrlError("This Amazon Music URL is not a track URL.")

    asin = ""
    if query_asins:
        asin = query_asins[0].strip().upper()
    elif path_match is not None:
        asin = path_match.group(1).upper()
    if not _ASIN_RE.fullmatch(asin):
        raise AmazonUrlError("This Amazon Music URL does not contain a valid track ASIN.")

    return AmazonTrackUrl(
        original=candidate,
        asin=asin,
        track_key=f"amazon:{asin}",
        canonical_url=f"https://music.amazon.com/tracks/{asin}",
    )
