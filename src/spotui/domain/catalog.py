"""Application-owned Amazon Music catalog types.

Provider adapters translate external response shapes into these types. API
schemas and the frontend consume them through explicit mappers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CatalogKind(StrEnum):
    ARTIST = "artist"
    ALBUM = "album"
    TRACK = "track"
    PLAYLIST = "playlist"
    COMMUNITY_PLAYLIST = "community_playlist"


DETAIL_KINDS: frozenset[CatalogKind] = frozenset(
    {
        CatalogKind.ARTIST,
        CatalogKind.ALBUM,
        CatalogKind.PLAYLIST,
        CatalogKind.COMMUNITY_PLAYLIST,
    }
)


@dataclass(frozen=True, slots=True)
class SearchItem:
    title: str
    subtitle: str
    url: str
    image: str | None
    kind: CatalogKind
    in_library: bool | None = None


@dataclass(frozen=True, slots=True)
class SearchSection:
    title: str
    kind: CatalogKind
    items: tuple[SearchItem, ...]


@dataclass(frozen=True, slots=True)
class TrackReference:
    title: str
    artist: str
    url: str
    image: str | None
    in_library: bool | None = None


@dataclass(frozen=True, slots=True)
class AlbumReference:
    title: str
    subtitle: str
    url: str
    image: str | None


@dataclass(frozen=True, slots=True)
class EntityDetail:
    kind: CatalogKind
    title: str
    subtitle: str
    image: str | None
    tracks: tuple[TrackReference, ...]
    albums: tuple[AlbumReference, ...]
