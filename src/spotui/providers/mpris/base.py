"""Application-owned Now Playing types and provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NowPlayingTrack:
    title: str
    artist: str
    track_id: str | None


@dataclass(frozen=True, slots=True)
class NowPlayingStatus:
    available: bool
    track: NowPlayingTrack | None
    player: str | None = None
    reason: str | None = None


class MprisProvider(Protocol):
    def now_playing(self) -> NowPlayingStatus: ...
