"""Amazon Music search use case with a small non-empty-result cache."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import replace

from spotui.domain.catalog import CatalogKind, SearchSection
from spotui.domain.errors import InvalidSearchQueryError
from spotui.providers.amazon.base import AmazonCatalog
from spotui.providers.library.base import LibraryLookup

_MAX_QUERY_LENGTH = 200
_DEFAULT_CACHE_SECONDS = 600.0


class SearchService:
    def __init__(
        self,
        provider: AmazonCatalog,
        *,
        library: LibraryLookup | None = None,
        cache_seconds: float = _DEFAULT_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = provider
        self._library = library
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, tuple[SearchSection, ...]]] = {}
        self._lock = threading.Lock()

    def search(self, query: str) -> tuple[SearchSection, ...]:
        normalized = " ".join(query.split())
        if not normalized:
            raise InvalidSearchQueryError("Enter a search query.")
        if len(normalized) > _MAX_QUERY_LENGTH:
            raise InvalidSearchQueryError("Search queries must be 200 characters or fewer.")

        key = normalized.casefold()
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                if now - cached[0] < self._cache_seconds:
                    return self._annotate(cached[1])
                del self._cache[key]

        sections = self._provider.search(normalized)
        if sections:
            with self._lock:
                self._cache[key] = (now, sections)
        return self._annotate(sections)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def _annotate(
        self, sections: tuple[SearchSection, ...]
    ) -> tuple[SearchSection, ...]:
        if self._library is None:
            return sections
        annotated = []
        for section in sections:
            items = tuple(
                replace(
                    item,
                    in_library=self._library.contains(
                        item.url,
                        item.title,
                        item.subtitle,
                    ),
                )
                if item.kind is CatalogKind.TRACK
                else item
                for item in section.items
            )
            annotated.append(replace(section, items=items))
        return tuple(annotated)
