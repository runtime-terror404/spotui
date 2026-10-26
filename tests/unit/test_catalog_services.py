from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from spotui.domain.amazon import AmazonUrl, AmazonUrlError
from spotui.domain.catalog import (
    CatalogKind,
    EntityDetail,
    SearchItem,
    SearchSection,
    TrackReference,
)
from spotui.domain.errors import InvalidSearchQueryError
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.search import SearchService


def section(title: str = "Songs") -> SearchSection:
    return SearchSection(
        title=title,
        kind=CatalogKind.TRACK,
        items=(
            SearchItem(
                title="Track",
                subtitle="Artist",
                url="https://music.amazon.com/tracks/B001",
                image=None,
                kind=CatalogKind.TRACK,
            ),
        ),
    )


DETAIL = EntityDetail(
    kind=CatalogKind.ALBUM,
    title="Album",
    subtitle="Artist",
    image=None,
    tracks=(
        TrackReference(
            title="Track",
            artist="Artist",
            url="https://music.amazon.com/tracks/B001",
            image=None,
        ),
    ),
    albums=(),
)


@dataclass
class FakeCatalog:
    sections: tuple[SearchSection, ...] = (section(),)
    search_calls: list[str] = field(default_factory=list)
    detail_calls: list[AmazonUrl] = field(default_factory=list)

    def search(self, query: str) -> tuple[SearchSection, ...]:
        self.search_calls.append(query)
        return self.sections

    def detail(self, target: AmazonUrl) -> EntityDetail:
        self.detail_calls.append(target)
        return DETAIL

    def close(self) -> None:
        pass


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_search_normalizes_caches_and_expires() -> None:
    provider = FakeCatalog()
    clock = Clock()
    service = SearchService(provider, cache_seconds=10, clock=clock)

    assert service.search("  Arijit   Singh ") == provider.sections
    assert service.search("arijit singh") == provider.sections
    assert provider.search_calls == ["Arijit Singh"]

    clock.now += 11
    service.search("Arijit Singh")
    assert provider.search_calls == ["Arijit Singh", "Arijit Singh"]


def test_empty_results_are_not_cached() -> None:
    provider = FakeCatalog(sections=())
    service = SearchService(provider)

    assert service.search("nothing") == ()
    assert service.search("nothing") == ()
    assert len(provider.search_calls) == 2


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
def test_invalid_queries_are_rejected(query: str) -> None:
    with pytest.raises(InvalidSearchQueryError):
        SearchService(FakeCatalog()).search(query)


def test_clear_cache_forces_provider_call() -> None:
    provider = FakeCatalog()
    service = SearchService(provider)

    service.search("query")
    service.clear_cache()
    service.search("query")

    assert len(provider.search_calls) == 2


def test_entity_detail_validates_and_dispatches() -> None:
    provider = FakeCatalog()
    service = EntityDetailsService(provider)

    assert service.detail("https://music.amazon.in/albums/B001") == DETAIL
    assert provider.detail_calls[0].kind is CatalogKind.ALBUM

    with pytest.raises(AmazonUrlError):
        service.detail("https://music.amazon.in/tracks/B001")
    with pytest.raises(AmazonUrlError):
        service.detail("https://example.com/albums/B001")
    assert len(provider.detail_calls) == 1


def test_services_close_resources_once_and_swallow_cleanup_errors() -> None:
    class Resource:
        def __init__(self, fail: bool = False) -> None:
            self.closed = 0
            self.fail = fail

        def close(self) -> None:
            self.closed += 1
            if self.fail:
                raise RuntimeError("cleanup failed")

    good = Resource()
    failing = Resource(fail=True)
    services = ApplicationServices(
        search=SearchService(FakeCatalog()),
        entity_details=EntityDetailsService(FakeCatalog()),
        resources=(good, failing),
    )

    services.close()
    services.close()

    assert good.closed == 1
    assert failing.closed == 1
