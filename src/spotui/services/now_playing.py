"""Now Playing use case."""

from __future__ import annotations

from spotui.providers.mpris.base import MprisProvider, NowPlayingStatus


class NowPlayingService:
    def __init__(self, provider: MprisProvider) -> None:
        self._provider = provider

    def status(self) -> NowPlayingStatus:
        return self._provider.now_playing()
