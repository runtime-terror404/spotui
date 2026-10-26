from __future__ import annotations

from dataclasses import dataclass, field

from spotui.domain.amazon import AmazonUrl
from spotui.domain.catalog import (
    AlbumReference,
    CatalogKind,
    EntityDetail,
    SearchItem,
    SearchSection,
    TrackReference,
)

DEFAULT_SECTIONS = (
    SearchSection(
        title="Artists",
        kind=CatalogKind.ARTIST,
        items=(
            SearchItem(
                title="Arijit Singh",
                subtitle="Artist",
                url="https://music.amazon.in/artists/B006ZO8YNU/arijit-singh",
                image="https://images.example/arijit.jpg",
                kind=CatalogKind.ARTIST,
            ),
        ),
    ),
    SearchSection(
        title="Albums",
        kind=CatalogKind.ALBUM,
        items=(
            SearchItem(
                title="Aashiqui 2",
                subtitle="Arijit Singh",
                url="https://music.amazon.in/albums/B001ALBUM",
                image="https://images.example/aashiqui.jpg",
                kind=CatalogKind.ALBUM,
            ),
        ),
    ),
    SearchSection(
        title="Songs",
        kind=CatalogKind.TRACK,
        items=(
            SearchItem(
                title="Tum Hi Ho",
                subtitle="Arijit Singh",
                url="https://music.amazon.in/albums/B001ALBUM?trackAsin=B002TRACK",
                image="https://images.example/tum.jpg",
                kind=CatalogKind.TRACK,
            ),
        ),
    ),
)

DEFAULT_DETAIL = EntityDetail(
    kind=CatalogKind.ALBUM,
    title="Aashiqui 2",
    subtitle="Arijit Singh",
    image="https://images.example/aashiqui.jpg",
    tracks=(
        TrackReference(
            title="Tum Hi Ho",
            artist="Arijit Singh",
            url="https://music.amazon.com/tracks/B002TRACK",
            image="https://images.example/aashiqui.jpg",
        ),
    ),
    albums=(
        AlbumReference(
            title="Aashiqui 2",
            subtitle="Album • 2013",
            url="https://music.amazon.in/albums/B001ALBUM",
            image="https://images.example/aashiqui.jpg",
        ),
    ),
)


@dataclass
class FakeWorker:
    started: int = 0
    stopped: int = 0
    wakes: int = 0
    cancels: list[str] = field(default_factory=list)
    active_job_id: str | None = None

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def wake(self) -> None:
        self.wakes += 1

    def cancel_active(self, job_id: str) -> None:
        self.cancels.append(job_id)


@dataclass
class FakeDownloader:
    available_value: bool = True
    cancel_calls: list[float] = field(default_factory=list)

    def available(self) -> bool:
        return self.available_value

    def run(self, url, on_phase):  # pragma: no cover - queue API tests do not run jobs
        raise NotImplementedError

    def cancel_active(self, grace_seconds: float) -> None:
        self.cancel_calls.append(grace_seconds)


@dataclass
class FakeLibrary:
    in_library: bool = False

    def contains(
        self,
        track_url: str,
        title: str | None = None,
        artist: str | None = None,
    ) -> bool:
        return self.in_library


@dataclass
class FakeCatalog:
    search_sections: tuple[SearchSection, ...] = DEFAULT_SECTIONS
    detail_result: EntityDetail = DEFAULT_DETAIL
    search_error: Exception | None = None
    detail_error: Exception | None = None
    search_calls: list[str] = field(default_factory=list)
    detail_calls: list[AmazonUrl] = field(default_factory=list)
    closed: int = 0

    def search(self, query: str) -> tuple[SearchSection, ...]:
        self.search_calls.append(query)
        if self.search_error is not None:
            raise self.search_error
        return self.search_sections

    def detail(self, target: AmazonUrl) -> EntityDetail:
        self.detail_calls.append(target)
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_result

    def close(self) -> None:
        self.closed += 1
