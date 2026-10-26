from __future__ import annotations

from typing import Protocol


class LibraryLookup(Protocol):
    def contains(
        self,
        track_url: str,
        title: str | None = None,
        artist: str | None = None,
    ) -> bool: ...
