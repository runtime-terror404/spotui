"""Provider contract consumed by catalog application services."""

from __future__ import annotations

from typing import Protocol

from spotui.domain.amazon import AmazonUrl
from spotui.domain.catalog import EntityDetail, SearchSection


class AmazonCatalog(Protocol):
    def search(self, query: str) -> tuple[SearchSection, ...]: ...

    def detail(self, target: AmazonUrl) -> EntityDetail: ...

    def close(self) -> None: ...
