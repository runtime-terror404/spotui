"""Typed Now Playing API contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from spotui.providers.mpris.base import NowPlayingStatus


class NowPlayingTrackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    artist: str
    track_id: str | None = None


class NowPlayingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    track: NowPlayingTrackResult | None = None
    player: str | None = None
    reason: str | None = None


def now_playing_response(status: NowPlayingStatus) -> NowPlayingResponse:
    return NowPlayingResponse(
        available=status.available,
        track=(
            NowPlayingTrackResult(
                title=status.track.title,
                artist=status.track.artist,
                track_id=status.track.track_id,
            )
            if status.track is not None
            else None
        ),
        player=status.player,
        reason=status.reason,
    )
