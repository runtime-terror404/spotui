"""Pure parsing of Amazon Music browser and lucida payloads.

These functions contain no browser or network access, which keeps the fragile
external response shapes testable with fixtures.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from spotui.domain.catalog import (
    AlbumReference,
    CatalogKind,
    EntityDetail,
    SearchItem,
    SearchSection,
    TrackReference,
)
from spotui.domain.errors import CatalogResponseError

AMAZON_BASE = "https://music.amazon.in"
_PAGE_TITLE_SUFFIX = " on Amazon Prime Music"
_TRACK_NUMBER_PREFIX = re.compile(r"^\d+\.\s*")
_TRAILING_INDEX = re.compile(r"(\d+)$")
_TOP_OFFSET = re.compile(r"top:\s*(-?\d+)px")

_HEADER_KINDS: dict[str, CatalogKind] = {
    "Artists": CatalogKind.ARTIST,
    "Albums": CatalogKind.ALBUM,
    "Songs": CatalogKind.TRACK,
    "Playlists": CatalogKind.PLAYLIST,
    "Community Playlists": CatalogKind.COMMUNITY_PLAYLIST,
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _image(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _absolute(deeplink: str) -> str:
    if deeplink.startswith("http"):
        return deeplink
    return AMAZON_BASE + deeplink


def classify_deeplink(deeplink: str) -> CatalogKind | None:
    if "/artists/" in deeplink:
        return CatalogKind.ARTIST
    if "trackAsin" in deeplink or "/tracks/" in deeplink:
        return CatalogKind.TRACK
    if "/user-playlists/" in deeplink:
        return CatalogKind.COMMUNITY_PLAYLIST
    if "/playlists/" in deeplink:
        return CatalogKind.PLAYLIST
    if "/albums/" in deeplink:
        return CatalogKind.ALBUM
    return None


def walk_items(obj: Any, output: list[dict[str, Any]], depth: int = 0) -> None:
    """Collect UI-item dictionaries from Amazon's nested payload."""
    if depth > 22:
        return
    if isinstance(obj, dict):
        primary_text = obj.get("primaryText")
        primary_link = obj.get("primaryLink")
        if (
            isinstance(primary_text, dict)
            and isinstance(primary_link, dict)
            and primary_link.get("deeplink")
        ):
            output.append(
                {
                    "title": _text(primary_text.get("text")),
                    "secondary": _text(obj.get("secondaryText")),
                    "deeplink": str(primary_link["deeplink"]),
                    "image": _text(obj.get("image")),
                }
            )
        for value in obj.values():
            walk_items(value, output, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            walk_items(value, output, depth + 1)


def widget_title(widget: Mapping[str, Any]) -> str:
    for key in ("title", "header"):
        value = widget.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = value.get("text") or value.get("title")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _widgets(data: Any) -> list[Any]:
    try:
        widgets = data["methods"][0]["template"]["widgets"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CatalogResponseError(
            "Amazon Music returned an unexpected search response."
        ) from exc
    if not isinstance(widgets, list):
        raise CatalogResponseError("Amazon Music returned an unexpected search response.")
    return widgets


def _section_accepts(section_kind: CatalogKind, item_kind: CatalogKind) -> bool:
    if section_kind is CatalogKind.PLAYLIST:
        return item_kind in (CatalogKind.PLAYLIST, CatalogKind.COMMUNITY_PLAYLIST)
    return section_kind is item_kind


def parse_search_payload(data: Any) -> tuple[SearchSection, ...]:
    sections: list[SearchSection] = []
    for widget in _widgets(data):
        if not isinstance(widget, dict):
            continue
        header = widget_title(widget)
        section_kind = _HEADER_KINDS.get(header)
        if section_kind is None:
            continue

        items: list[SearchItem] = []
        seen_urls: set[str] = set()
        raw_items = widget.get("items")
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            deeplink = str((raw_item.get("primaryLink") or {}).get("deeplink") or "")
            if not deeplink:
                continue
            item_kind = classify_deeplink(deeplink)
            if item_kind is None or not _section_accepts(section_kind, item_kind):
                continue
            primary_text = raw_item.get("primaryText") or {}
            title = _text(primary_text.get("text")) or _text(raw_item.get("imageAltText"))
            if not title:
                continue
            url = _absolute(deeplink)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                SearchItem(
                    title=title,
                    subtitle=_text(raw_item.get("secondaryText")),
                    url=url,
                    image=_image(raw_item.get("image")),
                    kind=item_kind,
                )
            )
        if items:
            sections.append(
                SearchSection(title=header, kind=section_kind, items=tuple(items))
            )
    return tuple(sections)


def parse_artist_payload(data: Any, page_title: str) -> EntityDetail:
    raw_items: list[dict[str, Any]] = []
    walk_items(data, raw_items)

    tracks: list[TrackReference] = []
    albums: list[AlbumReference] = []
    seen_tracks: set[str] = set()
    seen_albums: set[str] = set()
    for raw_item in raw_items:
        deeplink = raw_item["deeplink"]
        kind = classify_deeplink(deeplink)
        url = _absolute(deeplink)
        if kind is CatalogKind.TRACK and url not in seen_tracks:
            seen_tracks.add(url)
            tracks.append(
                TrackReference(
                    title=_TRACK_NUMBER_PREFIX.sub("", raw_item["title"]).strip(),
                    artist=raw_item["secondary"],
                    url=url,
                    image=_image(raw_item["image"]),
                )
            )
        elif kind is CatalogKind.ALBUM and url not in seen_albums:
            seen_albums.add(url)
            albums.append(
                AlbumReference(
                    title=raw_item["title"],
                    subtitle=raw_item["secondary"],
                    url=url,
                    image=_image(raw_item["image"]),
                )
            )

    if not tracks and not albums:
        raise CatalogResponseError("Amazon Music returned no artist content.")

    name = page_title.replace(_PAGE_TITLE_SUFFIX, "").strip() or "Artist"
    image = next(
        (
            reference.image
            for reference in (*tracks, *albums)
            if reference.image
        ),
        None,
    )
    return EntityDetail(
        kind=CatalogKind.ARTIST,
        title=name,
        subtitle="",
        image=image,
        tracks=tuple(tracks),
        albums=tuple(albums),
    )


def parse_community_playlist_rows(
    rows: Sequence[Mapping[str, Any]], page_title: str
) -> EntityDetail:
    found: dict[int, TrackReference] = {}
    for row in rows:
        title = _text(row.get("title"))
        href = _text(row.get("href"))
        if not title or not href:
            continue
        order_match = _TRAILING_INDEX.search(_text(row.get("key")))
        if order_match:
            order = int(order_match.group(1))
        else:
            top_match = _TOP_OFFSET.search(_text(row.get("style")))
            order = int(top_match.group(1)) if top_match else len(found)
        found.setdefault(
            order,
            TrackReference(
                title=title,
                artist=_text(row.get("artist")),
                url=_absolute(href),
                image=None,
            ),
        )

    if not found:
        raise CatalogResponseError("No tracks were found in this Amazon Music playlist.")
    title = page_title.split("|")[0].strip() or "Playlist"
    return EntityDetail(
        kind=CatalogKind.COMMUNITY_PLAYLIST,
        title=title,
        subtitle="",
        image=None,
        tracks=tuple(found[order] for order in sorted(found)),
        albums=(),
    )


def _artist_names(artists: Any) -> str:
    if not isinstance(artists, list):
        return ""
    return ", ".join(
        _text(artist.get("name"))
        for artist in artists
        if isinstance(artist, dict) and _text(artist.get("name"))
    )


def parse_lucida_info(info: Any) -> EntityDetail:
    if not isinstance(info, Mapping):
        raise CatalogResponseError("The Amazon catalog resolver returned an invalid response.")
    item_type = info.get("type")
    if item_type not in ("album", "playlist"):
        raise CatalogResponseError("This Amazon Music item has no downloadable track list.")
    kind = CatalogKind.ALBUM if item_type == "album" else CatalogKind.PLAYLIST

    album_artists = _text(info.get("artist")) or _artist_names(info.get("artists"))
    cover = _image(info.get("cover")) or _image(info.get("coverArtwork"))
    tracks: list[TrackReference] = []
    raw_tracks = info.get("tracks")
    if isinstance(raw_tracks, list):
        for raw_track in raw_tracks:
            if not isinstance(raw_track, Mapping):
                continue
            title = _text(raw_track.get("title"))
            url = _text(raw_track.get("url"))
            if not title or not url:
                continue
            artist = (
                _text(raw_track.get("artist"))
                or _artist_names(raw_track.get("artists"))
                or album_artists
            )
            tracks.append(
                TrackReference(title=title, artist=artist, url=url, image=cover)
            )
    if not tracks:
        raise CatalogResponseError("No downloadable tracks were returned for this item.")

    return EntityDetail(
        kind=kind,
        title=_text(info.get("title")),
        subtitle=album_artists,
        image=cover,
        tracks=tuple(tracks),
        albums=(),
    )
