"""Amazon catalog facade choosing browser or managed-resolver detail paths."""

from __future__ import annotations

from spotui.domain.amazon import AmazonUrl
from spotui.domain.catalog import CatalogKind, EntityDetail, SearchSection
from spotui.domain.errors import CatalogResponseError
from spotui.providers.amazon.browser import AmazonBrowserProvider
from spotui.providers.amazon.lucida import LucidaDetailProvider


class AmazonCatalogProvider:
    def __init__(
        self,
        browser: AmazonBrowserProvider,
        lucida: LucidaDetailProvider,
    ) -> None:
        self._browser = browser
        self._lucida = lucida

    def search(self, query: str) -> tuple[SearchSection, ...]:
        return self._browser.search(query)

    def detail(self, target: AmazonUrl) -> EntityDetail:
        if target.kind is CatalogKind.ARTIST:
            return self._browser.artist_detail(target.original)
        if target.kind is CatalogKind.COMMUNITY_PLAYLIST:
            return self._browser.community_playlist_detail(target.original)
        if target.kind in (CatalogKind.ALBUM, CatalogKind.PLAYLIST):
            return self._lucida.resolve(target.original)
        raise CatalogResponseError("This Amazon Music item has no detail view.")

    def close(self) -> None:
        self._browser.close()
