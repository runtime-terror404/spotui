"""Application-owned audio tag types and provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AudioTagMetadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    track_number: str = ""
    duration_seconds: float | None = None
    amazon_track_key: str | None = None


class AudioTagReader(Protocol):
    def read(self, path: Path) -> AudioTagMetadata: ...
