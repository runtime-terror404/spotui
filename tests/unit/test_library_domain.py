from __future__ import annotations

from pathlib import Path

from spotui.domain.library import (
    LibraryLookupResult,
    LibraryMatch,
    artist_from_path,
    normalize_library_text,
    normalized_artist_tokens,
    title_from_filename,
)


def test_normalization_ignores_case_brackets_and_punctuation() -> None:
    assert normalize_library_text("  Song (Live) [Remastered]! ") == "song"
    assert normalize_library_text("Rock & Roll") == "rock roll"
    assert normalized_artist_tokens("Arijit Singh, Other") == {"arijit", "singh", "other"}


def test_filename_title_removes_common_track_prefixes() -> None:
    assert title_from_filename(Path("01 - Tum Hi Ho.flac")) == "Tum Hi Ho"
    assert title_from_filename(Path("A01. Tum Hi Ho.flac")) == "Tum Hi Ho"
    assert title_from_filename(Path("Tum Hi Ho.flac")) == "Tum Hi Ho"


def test_artist_is_inferred_from_organized_path_or_filename(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    organized = root / "Artists" / "Arijit Singh" / "Aashiqui 2" / "Tum Hi Ho.flac"
    flat = root / "Arijit Singh - Tum Hi Ho.flac"

    assert artist_from_path(root, organized, "Tum Hi Ho") == "Arijit Singh"
    assert artist_from_path(root, flat, "Tum Hi Ho") == "Arijit Singh"
    assert artist_from_path(root, root / "Unknown.flac", "Unknown") == ""


def test_lookup_result_distinguishes_absent_from_unknown() -> None:
    assert LibraryLookupResult(LibraryMatch.EXACT, True).in_library is True
    assert LibraryLookupResult(None, True).in_library is False
    assert LibraryLookupResult(None, False).in_library is None
