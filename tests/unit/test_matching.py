from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from spotui.domain.catalog import CatalogKind, SearchItem, SearchSection
from spotui.domain.errors import CatalogTimeoutError
from spotui.services.matching import MatchingService, score_candidate
from spotui.services.search import SearchService


def track(title: str, artist: str, asin: str, image: str | None = None) -> SearchItem:
    return SearchItem(
        title=title,
        subtitle=artist,
        url=f"https://music.amazon.com/tracks/{asin}",
        image=image,
        kind=CatalogKind.TRACK,
    )


def results(*items: SearchItem) -> tuple[SearchSection, ...]:
    return (
        SearchSection(
            title="Songs",
            kind=CatalogKind.TRACK,
            items=items,
        ),
    )


@dataclass
class ScriptedCatalog:
    responses: dict[str, tuple[SearchSection, ...] | Exception]
    calls: list[str] = field(default_factory=list)

    def search(self, query: str) -> tuple[SearchSection, ...]:
        self.calls.append(query)
        response = self.responses.get(query, ())
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        pass


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def service_for(catalog: ScriptedCatalog, **kwargs) -> MatchingService:
    return MatchingService(SearchService(catalog), **kwargs)


def test_candidates_are_ranked_deterministically_without_auto_selection() -> None:
    catalog = ScriptedCatalog(
        {
            "Arijit Singh Tum Hi Ho": results(
                track("Tum Hi Ho (Live)", "Arijit Singh", "B000000003", "live.jpg"),
                track("Tum Hi Ho", "Arijit Singh", "B000000001", "exact.jpg"),
                track("Tum Hi Ho", "Other Artist", "B000000002"),
            )
        }
    )

    candidates = service_for(catalog).find_candidates(
        title="Tum Hi Ho",
        artist="Arijit Singh",
    )

    assert [candidate.track_key for candidate in candidates] == [
        "amazon:B000000001",
        "amazon:B000000002",
        "amazon:B000000003",
    ]
    assert [candidate.rank for candidate in candidates] == [1, 2, 3]
    assert candidates[0].score > candidates[1].score
    assert candidates[0].explanation == "Exact title with a matching artist"
    assert "version metadata differs" in candidates[2].explanation
    assert candidates[0].artwork_url == "exact.jpg"


def test_title_fallback_runs_when_artist_query_has_no_tracks() -> None:
    catalog = ScriptedCatalog(
        {
            "Arijit Singh Tum Hi Ho": (),
            "Tum Hi Ho": results(track("Tum Hi Ho", "Arijit Singh", "B000000001")),
        }
    )

    candidates = service_for(catalog).find_candidates(
        title="Tum Hi Ho",
        artist="Arijit Singh",
    )

    assert catalog.calls == ["Arijit Singh Tum Hi Ho", "Tum Hi Ho"]
    assert len(candidates) == 1


def test_candidates_are_deduplicated_and_invalid_urls_are_ignored() -> None:
    catalog = ScriptedCatalog(
        {
            "Artist Song": (
                SearchSection(
                    title="Songs",
                    kind=CatalogKind.TRACK,
                    items=(
                        track("Song", "Artist", "B000000001"),
                        SearchItem(
                            title="Song",
                            subtitle="Artist",
                            url="https://example.com/track",
                            image=None,
                            kind=CatalogKind.TRACK,
                        ),
                        SearchItem(
                            title="Song duplicate",
                            subtitle="Artist",
                            url="https://music.amazon.in/albums/B1?trackAsin=B000000001",
                            image=None,
                            kind=CatalogKind.TRACK,
                        ),
                    ),
                ),
            )
        }
    )

    candidates = service_for(catalog).find_candidates(title="Song", artist="Artist")

    assert len(candidates) == 1
    assert candidates[0].track_key == "amazon:B000000001"


def test_transient_search_errors_retry_with_backoff() -> None:
    catalog = ScriptedCatalog(
        {
            "Artist Song": CatalogTimeoutError("Amazon timed out."),
        }
    )
    catalog.responses["Artist Song"] = CatalogTimeoutError("Amazon timed out.")
    sleep = RecordingSleep()
    matching = service_for(catalog, attempts=2, backoff_seconds=0.5, sleep=sleep)

    with pytest.raises(CatalogTimeoutError):
        matching.find_candidates(title="Song", artist="Artist")

    assert catalog.calls == ["Artist Song", "Artist Song"]
    assert sleep.calls == [0.5]


def test_version_penalty_and_artist_overlap_affect_scores() -> None:
    exact_score, _ = score_candidate(
        source_title="Song",
        source_artist="Artist",
        candidate_title="Song",
        candidate_artist="Artist",
    )
    version_score, explanation = score_candidate(
        source_title="Song",
        source_artist="Artist",
        candidate_title="Song (Live)",
        candidate_artist="Artist",
    )
    wrong_artist_score, _ = score_candidate(
        source_title="Song",
        source_artist="Artist",
        candidate_title="Song",
        candidate_artist="Different",
    )

    assert exact_score > version_score
    assert exact_score > wrong_artist_score
    assert "version metadata differs" in explanation
    assert 0 <= wrong_artist_score <= 1


def test_search_queries_are_bounded_in_length() -> None:
    catalog = ScriptedCatalog({})
    title = "T" * 150
    artist = "A" * 150
    service_for(catalog).find_candidates(title=title, artist=artist)

    assert all(len(query) <= 200 for query in catalog.calls)
