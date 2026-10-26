"""Application-owned library index types and normalization rules."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class LibraryMatch(StrEnum):
    """How strongly an indexed file matches an Amazon track."""

    EXACT = "exact"
    LIKELY = "likely"


class LibraryScanStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class LibraryMetadataSource(StrEnum):
    TAGS = "tags"
    FILENAME = "filename"


@dataclass(frozen=True, slots=True)
class LibraryLookupResult:
    """A match plus whether every configured root has a complete index."""

    match: LibraryMatch | None
    complete: bool

    @property
    def in_library(self) -> bool | None:
        if self.match is not None:
            return True
        return False if self.complete else None


@dataclass(frozen=True, slots=True)
class LibraryRoot:
    id: int
    path: str
    available: bool
    index_complete: bool
    last_checked_at: int | None
    last_scan_at: int | None
    file_count: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class LibraryScan:
    id: int
    root_id: int
    status: LibraryScanStatus
    started_at: int
    finished_at: int | None
    files_seen: int
    files_indexed: int
    files_removed: int
    files_failed: int
    error: str | None


@dataclass(frozen=True, slots=True)
class LibraryOverview:
    roots: tuple[LibraryRoot, ...]
    active_scan: LibraryScan | None

    @property
    def total_files(self) -> int:
        return sum(root.file_count for root in self.roots)

    @property
    def unavailable_roots(self) -> int:
        return sum(1 for root in self.roots if not root.available)


@dataclass(frozen=True, slots=True)
class LibraryFileMetadata:
    path: str
    filename: str
    extension: str
    size_bytes: int
    modified_at_ns: int
    title: str
    artist: str
    album: str
    track_number: str
    duration_seconds: float | None
    metadata_source: LibraryMetadataSource
    normalized_title: str
    normalized_artist: str
    amazon_track_key: str | None


_BRACKETED_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)
_TRACK_PREFIX_RE = re.compile(r"^\s*(?:\d{1,3}|[A-Za-z]\d{1,3})\s*[-._ ]\s+")


def normalize_library_text(value: str | None) -> str:
    """Normalize a title or artist for comparison, not for display."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = _BRACKETED_RE.sub(" ", normalized)
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def normalized_artist_tokens(value: str | None) -> frozenset[str]:
    normalized = normalize_library_text(value)
    return frozenset(normalized.split()) if normalized else frozenset()


def title_from_filename(path: Path) -> str:
    """Use a filename as a readable title when audio tags are absent."""
    stem = path.stem.strip()
    return _TRACK_PREFIX_RE.sub("", stem).strip() or stem


def artist_from_path(root: Path, path: Path, title: str) -> str:
    """Infer an artist from the organized path or an ``Artist - Title`` name."""
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    for index, part in enumerate(relative_parts[:-1]):
        if part.casefold() == "artists" and index + 1 < len(relative_parts) - 1:
            return relative_parts[index + 1].strip()
    stem = path.stem
    if " - " in stem:
        candidate = stem.split(" - ", 1)[0].strip()
        if candidate and candidate != title:
            return candidate
    return ""
