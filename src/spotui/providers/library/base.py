from __future__ import annotations

from typing import Protocol

from spotui.domain.library import LibraryLookupResult


class LibraryLookup(Protocol):
    def lookup(
        self,
        track_url: str,
        title: str | None = None,
        artist: str | None = None,
    ) -> LibraryLookupResult: ...
