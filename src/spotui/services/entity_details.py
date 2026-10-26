"""Amazon Music entity-detail use case."""

from __future__ import annotations

from dataclasses import replace

from spotui.domain.amazon import AmazonUrlError, parse_amazon_url
from spotui.domain.catalog import DETAIL_KINDS, EntityDetail
from spotui.providers.amazon.base import AmazonCatalog
from spotui.providers.library.base import LibraryLookup


class EntityDetailsService:
    def __init__(
        self,
        provider: AmazonCatalog,
        *,
        library: LibraryLookup | None = None,
    ) -> None:
        self._provider = provider
        self._library = library

    def detail(self, url: str) -> EntityDetail:
        target = parse_amazon_url(url)
        if target.kind not in DETAIL_KINDS:
            raise AmazonUrlError("This Amazon Music URL does not have a detail view.")
        detail = self._provider.detail(target)
        if self._library is None:
            return detail
        tracks = []
        for track in detail.tracks:
            lookup = self._library.lookup(track.url, track.title, track.artist)
            tracks.append(
                replace(
                    track,
                    in_library=lookup.in_library,
                    library_match=lookup.match,
                )
            )
        return replace(detail, tracks=tuple(tracks))
