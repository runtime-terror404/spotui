"""Strict validation and classification of Amazon Music URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from spotui.domain.catalog import CatalogKind

ALLOWED_AMAZON_HOSTS = frozenset({"music.amazon.com", "music.amazon.in"})

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


def parse_amazon_url(raw_url: str) -> AmazonUrl:
    """Validate scheme, credentials, host, and supported entity path."""
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

    kind = next(
        (candidate_kind for pattern, candidate_kind in _PATH_KINDS if pattern.match(parsed.path)),
        None,
    )
    if kind is None:
        raise AmazonUrlError("This Amazon Music URL does not identify a supported item.")
    return AmazonUrl(original=candidate, host=host, path=parsed.path, kind=kind)
