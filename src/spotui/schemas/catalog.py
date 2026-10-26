"""Typed API contracts for search and entity details."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from spotui.domain.catalog import (
    CatalogKind,
    EntityDetail,
    SearchSection,
)


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    subtitle: str = ""
    url: str
    image: str | None = None
    kind: CatalogKind
    in_library: bool | None = None


class SearchSectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    kind: CatalogKind
    items: list[CatalogItem]


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    sections: list[SearchSectionResult]


class TrackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    artist: str
    url: str
    image: str | None = None
    in_library: bool | None = None


class AlbumResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    subtitle: str
    url: str
    image: str | None = None


class EntityDetailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CatalogKind
    title: str
    subtitle: str
    image: str | None = None
    tracks: list[TrackResult]
    albums: list[AlbumResult]


def search_response(
    query: str, sections: tuple[SearchSection, ...]
) -> SearchResponse:
    return SearchResponse(
        query=query,
        sections=[
            SearchSectionResult(
                title=section.title,
                kind=section.kind,
                items=[
                    CatalogItem(
                        title=item.title,
                        subtitle=item.subtitle,
                        url=item.url,
                        image=item.image,
                        kind=item.kind,
                    )
                    for item in section.items
                ],
            )
            for section in sections
        ],
    )


def entity_detail_response(detail: EntityDetail) -> EntityDetailResult:
    return EntityDetailResult(
        kind=detail.kind,
        title=detail.title,
        subtitle=detail.subtitle,
        image=detail.image,
        tracks=[
            TrackResult(
                title=track.title,
                artist=track.artist,
                url=track.url,
                image=track.image,
            )
            for track in detail.tracks
        ],
        albums=[
            AlbumResult(
                title=album.title,
                subtitle=album.subtitle,
                url=album.url,
                image=album.image,
            )
            for album in detail.albums
        ],
    )
