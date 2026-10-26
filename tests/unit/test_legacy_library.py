from __future__ import annotations

import json
from pathlib import Path

from spotui.providers.library.legacy import (
    LegacyLibraryIndex,
    default_lucidadl_state_file,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def make_state(tmp_path: Path, entries: dict[str, list[str]]) -> Path:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"done": entries}), encoding="utf-8")
    return state


def make_media(tmp_path: Path, relative: str) -> Path:
    path = tmp_path / "Music" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    return path


def test_asin_match_requires_existing_file(tmp_path: Path) -> None:
    media = make_media(tmp_path, "Artists/Artist/Album/Song.flac")
    state = make_state(
        tmp_path,
        {
            "https://music.amazon.com/tracks/B002TRACK1": [str(media)],
            "https://music.amazon.com/tracks/B003TRACK2": [str(tmp_path / "missing.flac")],
        },
    )
    index = LegacyLibraryIndex(state)

    assert index.contains("https://music.amazon.in/albums/B1?trackAsin=B002TRACK1") is True
    assert index.contains("https://music.amazon.in/albums/B1?trackAsin=B003TRACK2") is False


def test_title_and_artist_fallback(tmp_path: Path) -> None:
    media = make_media(tmp_path, "Artists/Arijit Singh/Aashiqui 2/Song (Live).flac")
    state = make_state(
        tmp_path,
        {"https://music.amazon.com/albums/B001": [str(media)]},
    )
    index = LegacyLibraryIndex(state)

    assert index.contains("https://music.amazon.com/tracks/ZZZZZZZZZZ", "Song", "Arijit Singh")
    assert index.contains(
        "https://music.amazon.com/tracks/ZZZZZZZZZZ",
        "Song",
        "Arijit Singh, Other",
    )
    assert not index.contains(
        "https://music.amazon.com/tracks/ZZZZZZZZZZ",
        "Song",
        "Different Artist",
    )


def test_missing_or_invalid_state_is_empty(tmp_path: Path) -> None:
    missing = LegacyLibraryIndex(tmp_path / "missing.json")
    invalid_state = tmp_path / "invalid.json"
    invalid_state.write_text("not-json", encoding="utf-8")
    invalid = LegacyLibraryIndex(invalid_state)

    assert not missing.contains("https://music.amazon.com/tracks/B002TRACK1", "Song")
    assert not invalid.contains("https://music.amazon.com/tracks/B002TRACK1", "Song")


def test_refresh_interval_picks_up_new_entries(tmp_path: Path) -> None:
    clock = Clock()
    state = make_state(tmp_path, {})
    index = LegacyLibraryIndex(state, refresh_seconds=10, clock=clock)
    assert not index.contains("https://music.amazon.com/tracks/B002TRACK1")

    media = make_media(tmp_path, "Artists/Artist/Album/Song.flac")
    state.write_text(
        json.dumps(
            {"done": {"https://music.amazon.com/tracks/B002TRACK1": [str(media)]}}
        ),
        encoding="utf-8",
    )
    assert not index.contains("https://music.amazon.com/tracks/B002TRACK1")

    clock.now += 11
    assert index.contains("https://music.amazon.com/tracks/B002TRACK1")


def test_default_state_path_honors_environment(tmp_path: Path) -> None:
    override = tmp_path / "lucida"
    assert default_lucidadl_state_file({"LUCIDADL_HOME": str(override)}) == (
        override / "state.json"
    )
    data_home = tmp_path / "data"
    assert default_lucidadl_state_file({"XDG_DATA_HOME": str(data_home)}) == (
        data_home / "lucidadl" / "state.json"
    )
