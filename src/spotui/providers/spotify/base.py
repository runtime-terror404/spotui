"""Spotify provider contract."""

from __future__ import annotations

from typing import Protocol

from spotui.domain.spotify import SpotifyCollection


class SpotifyProvider(Protocol):
    def extract(self, url: str) -> SpotifyCollection: ...
