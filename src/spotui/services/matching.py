"""Ranked Amazon candidate search for Spotify source occurrences."""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher

from spotui.domain.amazon import AmazonUrlError, parse_amazon_track_url
from spotui.domain.catalog import CatalogKind
from spotui.domain.errors import CatalogError
from spotui.domain.imports import CandidateDraft
from spotui.services.search import SearchService

MAX_CANDIDATES = 10
MATCH_ATTEMPTS = 2
MATCH_BACKOFF_SECONDS = 0.5
_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)
_VERSION_RE = re.compile(
    r"\b(?:live|remix|instrumental|acoustic|karaoke|cover|extended|edit|"
    r"remaster(?:ed)?|sped\s+up|slowed|reverb|demo)\b",
    re.IGNORECASE,
)


def _match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_match_text(value).split())


def _version_tokens(value: str) -> frozenset[str]:
    return frozenset(match.group(0).casefold() for match in _VERSION_RE.finditer(value))


def _artist_similarity(source: str, candidate: str) -> float:
    source_tokens = _tokens(source)
    candidate_tokens = _tokens(candidate)
    if not source_tokens or not candidate_tokens:
        return 0.0
    return len(source_tokens & candidate_tokens) / len(source_tokens | candidate_tokens)


def score_candidate(
    *,
    source_title: str,
    source_artist: str,
    candidate_title: str,
    candidate_artist: str,
) -> tuple[float, str]:
    source_text = _match_text(source_title)
    candidate_text = _match_text(candidate_title)
    title_ratio = (
        SequenceMatcher(None, source_text, candidate_text).ratio()
        if source_text and candidate_text
        else 0.0
    )
    artist_ratio = _artist_similarity(source_artist, candidate_artist)
    exact_title = 1.0 if source_text and source_text == candidate_text else 0.0
    version_source = _version_tokens(source_title)
    version_candidate = _version_tokens(candidate_title)
    version_penalty = 0.08 * len(version_source.symmetric_difference(version_candidate))
    score = (
        0.65 * title_ratio
        + 0.2 * artist_ratio
        + 0.1 * exact_title
        + 0.05 * (1.0 if exact_title and artist_ratio > 0 else 0.0)
        - version_penalty
    )
    score = max(0.0, min(1.0, round(score, 4)))

    if exact_title and artist_ratio > 0:
        explanation = "Exact title with a matching artist"
    elif exact_title:
        explanation = "Exact title match"
    elif artist_ratio > 0 and title_ratio >= 0.6:
        explanation = "Close title match with matching artist"
    elif title_ratio >= 0.6:
        explanation = "Close title match"
    else:
        explanation = "Provider search result"
    if version_source != version_candidate:
        explanation += "; version metadata differs"
    return score, explanation


class MatchingService:
    def __init__(
        self,
        search: SearchService,
        *,
        attempts: int = MATCH_ATTEMPTS,
        backoff_seconds: float = MATCH_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        max_candidates: int = MAX_CANDIDATES,
    ) -> None:
        self._search = search
        self._attempts = max(1, attempts)
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep
        self._max_candidates = max(1, max_candidates)

    def find_candidates(
        self,
        *,
        title: str,
        artist: str,
        duration_seconds: float | None = None,
    ) -> tuple[CandidateDraft, ...]:
        # Amazon search rows do not expose durations; the field is retained for
        # the provider contract so richer candidates can be ranked later.
        del duration_seconds
        queries = self._queries(title, artist)
        if not queries:
            return ()
        last_error: CatalogError | None = None
        for attempt in range(self._attempts):
            try:
                items = self._collect(queries[0])
                if not items and len(queries) > 1:
                    items = self._collect(queries[1])
                return self._rank(title, artist, items)
            except CatalogError as exc:
                last_error = exc
                if attempt + 1 < self._attempts:
                    self._sleep(self._backoff_seconds * (2**attempt))
        if last_error is not None:
            raise last_error
        return ()

    def _collect(self, query: str) -> list[tuple[str, str, str, str | None]]:
        sections = self._search.search(query)
        items: list[tuple[str, str, str, str | None]] = []
        seen: set[str] = set()
        for section in sections:
            if section.kind is not CatalogKind.TRACK:
                continue
            for item in section.items:
                if item.kind is not CatalogKind.TRACK:
                    continue
                try:
                    track = parse_amazon_track_url(item.url)
                except AmazonUrlError:
                    continue
                if track.track_key in seen:
                    continue
                seen.add(track.track_key)
                items.append((track.original, item.title, item.subtitle, item.image))
        return items

    def _rank(
        self,
        source_title: str,
        source_artist: str,
        items: Sequence[tuple[str, str, str, str | None]],
    ) -> tuple[CandidateDraft, ...]:
        scored: list[tuple[float, int, CandidateDraft]] = []
        for position, (url, title, artist, artwork) in enumerate(items):
            score, explanation = score_candidate(
                source_title=source_title,
                source_artist=source_artist,
                candidate_title=title,
                candidate_artist=artist,
            )
            try:
                track = parse_amazon_track_url(url)
            except AmazonUrlError:
                continue
            draft = CandidateDraft(
                track_url=track.original,
                track_key=track.track_key,
                title=title,
                artist=artist,
                album="",
                duration_seconds=None,
                artwork_url=artwork,
                provider_position=position,
                rank=0,
                score=score,
                explanation=explanation,
            )
            scored.append((score, position, draft))
        scored.sort(key=lambda item: (-item[0], item[1]))
        ranked: list[CandidateDraft] = []
        for rank, (score, _position, draft) in enumerate(
            scored[: self._max_candidates],
            start=1,
        ):
            ranked.append(
                CandidateDraft(
                    track_url=draft.track_url,
                    track_key=draft.track_key,
                    title=draft.title,
                    artist=draft.artist,
                    album=draft.album,
                    duration_seconds=draft.duration_seconds,
                    artwork_url=draft.artwork_url,
                    provider_position=draft.provider_position,
                    rank=rank,
                    score=score,
                    explanation=draft.explanation,
                )
            )
        return tuple(ranked)

    @staticmethod
    def _queries(title: str, artist: str) -> list[str]:
        clean_title = " ".join(title.split())
        clean_artist = " ".join(artist.split())
        queries: list[str] = []
        if clean_title and clean_artist:
            queries.append(f"{clean_artist} {clean_title}"[:200].strip())
        if clean_title:
            title_query = clean_title[:200].strip()
            if title_query not in queries:
                queries.append(title_query)
        return queries
