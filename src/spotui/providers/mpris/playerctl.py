"""playerctl-backed MPRIS metadata adapter.

Missing playerctl, a missing desktop session, and an idle/absent player are
normal states, not application failures. They are returned as explicit
availability information so search and downloads continue to work.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Sequence

from spotui.providers.mpris.base import (
    MprisProvider,
    NowPlayingStatus,
    NowPlayingTrack,
)

logger = logging.getLogger("spotui.mpris.playerctl")

Runner = Callable[..., subprocess.CompletedProcess[str]]
_PREFERRED_PLAYER_FRAGMENTS = ("spotify", "spotifast", "spot")


class _Unavailable(RuntimeError):
    pass


class PlayerctlMprisProvider(MprisProvider):
    def __init__(
        self,
        *,
        executable: str = "playerctl",
        runner: Runner = subprocess.run,
        timeout: float = 3.0,
        player_override: str | None = None,
    ) -> None:
        self._executable = executable
        self._runner = runner
        self._timeout = timeout
        if player_override is None:
            player_override = (
                os.environ.get("SPOTUI_MPRIS_PLAYER", "").strip()
                or os.environ.get("SPOTGRAB_PLAYER", "").strip()
                or None
            )
        self._player_override = player_override

    def now_playing(self) -> NowPlayingStatus:
        try:
            player = self._player_override or self._detect_player()
        except _Unavailable as exc:
            return NowPlayingStatus(False, None, None, str(exc))
        if player is None:
            return NowPlayingStatus(True, None, None, "No media player is running.")

        status = self._run(["-p", player, "status"])
        if status.returncode != 0:
            return NowPlayingStatus(True, None, player, "The media player is not responding.")
        state = status.stdout.strip()
        if state not in ("Playing", "Paused"):
            return NowPlayingStatus(True, None, player, "Nothing is playing.")

        title = self._metadata(player, "xesam:title")
        if not title:
            return NowPlayingStatus(
                True,
                None,
                player,
                "The media player has no track metadata.",
            )
        artist = self._metadata(player, "xesam:artist")
        track_id = (
            self._metadata(player, "mpris:trackid")
            or self._metadata(player, "xesam:url")
            or None
        )
        return NowPlayingStatus(
            True,
            NowPlayingTrack(title=title, artist=artist, track_id=track_id),
            player,
            None,
        )

    def _detect_player(self) -> str | None:
        result = self._run(["-l"])
        if result.returncode != 0:
            raise _Unavailable("Could not query MPRIS media players.")
        players = [player for player in result.stdout.split() if player]
        if not players:
            return None
        for fragment in _PREFERRED_PLAYER_FRAGMENTS:
            for player in players:
                if fragment in player.lower():
                    return player
        return players[0]

    def _metadata(self, player: str, key: str) -> str:
        result = self._run(["-p", player, "metadata", key])
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _run(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                [self._executable, *arguments],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise _Unavailable("playerctl is not installed.") from exc
        except subprocess.TimeoutExpired as exc:
            raise _Unavailable("The MPRIS query timed out.") from exc
        except OSError as exc:
            logger.warning("MPRIS query failed: %s", exc.__class__.__name__)
            raise _Unavailable("MPRIS is unavailable.") from exc
