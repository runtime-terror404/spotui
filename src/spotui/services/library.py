"""Library index use cases and lookup contract."""

from __future__ import annotations

from spotui.domain.amazon import AmazonUrlError, parse_amazon_track_url
from spotui.domain.library import (
    LibraryLookupResult,
    LibraryOverview,
    normalize_library_text,
    normalized_artist_tokens,
)
from spotui.persistence.repositories.library import LibraryRepository
from spotui.workers.library_scanner import LibraryScanWorker


class LibraryService:
    def __init__(
        self,
        repository: LibraryRepository,
        scanner: LibraryScanWorker,
    ) -> None:
        self._repository = repository
        self._scanner = scanner

    def start(self) -> None:
        self._scanner.start()

    def close(self) -> None:
        self._scanner.close()

    def overview(self) -> LibraryOverview:
        return LibraryOverview(
            roots=self._repository.list_roots(),
            active_scan=self._repository.active_scan(),
        )

    def request_scan(self) -> bool:
        return self._scanner.request_scan()

    def lookup(
        self,
        track_url: str,
        title: str | None = None,
        artist: str | None = None,
    ) -> LibraryLookupResult:
        try:
            track_key: str | None = parse_amazon_track_url(track_url).track_key
        except AmazonUrlError:
            track_key = None
        return self._repository.lookup(
            amazon_track_key=track_key,
            normalized_title=normalize_library_text(title),
            artist_tokens=normalized_artist_tokens(artist),
        )
