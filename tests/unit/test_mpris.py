from __future__ import annotations

import subprocess
from typing import Any

import pytest

from spotui.providers.mpris.playerctl import PlayerctlMprisProvider


class Runner:
    def __init__(self, responses: dict[tuple[str, ...], Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        response = self.responses.get(tuple(command))
        if isinstance(response, Exception):
            raise response
        assert response is not None, f"unexpected command: {command}"
        return response


def completed(command: list[str], stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def playing_responses(
    player: str = "spotifast",
    *,
    status: str = "Playing",
    title: str = "Tum Hi Ho",
    artist: str = "Arijit Singh",
    track_id: str = "spotify:track:abc",
) -> dict[tuple[str, ...], Any]:
    return {
        ("playerctl", "-l"): completed(["playerctl", "-l"], f"{player}\nmpv\n"),
        ("playerctl", "-p", player, "status"): completed([], status),
        ("playerctl", "-p", player, "metadata", "xesam:title"): completed([], title),
        ("playerctl", "-p", player, "metadata", "xesam:artist"): completed([], artist),
        ("playerctl", "-p", player, "metadata", "mpris:trackid"): completed([], track_id),
        ("playerctl", "-p", player, "metadata", "xesam:url"): completed([], ""),
    }


def test_playing_track_is_detected_and_prefers_spotify_clients() -> None:
    runner = Runner(playing_responses())

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.available is True
    assert status.player == "spotifast"
    assert status.track is not None
    assert status.track.title == "Tum Hi Ho"
    assert status.track.artist == "Arijit Singh"
    assert status.track.track_id == "spotify:track:abc"
    assert status.reason is None
    command, kwargs = runner.calls[0]
    assert command == ["playerctl", "-l"]
    assert "shell" not in kwargs


def test_paused_player_is_accepted() -> None:
    status = PlayerctlMprisProvider(
        runner=Runner(playing_responses(status="Paused"))
    ).now_playing()

    assert status.track is not None


def test_stopped_player_has_no_track() -> None:
    status = PlayerctlMprisProvider(
        runner=Runner(playing_responses(status="Stopped"))
    ).now_playing()

    assert status.available is True
    assert status.track is None
    assert status.reason == "Nothing is playing."


def test_no_players_is_explicit_but_available() -> None:
    runner = Runner({("playerctl", "-l"): completed([], "", 0)})

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.available is True
    assert status.track is None
    assert status.reason == "No media player is running."


def test_missing_playerctl_is_explicitly_unavailable() -> None:
    runner = Runner({("playerctl", "-l"): FileNotFoundError("playerctl")})

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.available is False
    assert status.track is None
    assert status.reason == "playerctl is not installed."


def test_timeout_is_explicitly_unavailable() -> None:
    runner = Runner(
        {("playerctl", "-l"): subprocess.TimeoutExpired(["playerctl", "-l"], 3)}
    )

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.available is False
    assert "timed out" in (status.reason or "")


def test_player_list_failure_is_unavailable() -> None:
    runner = Runner({("playerctl", "-l"): completed([], "", 1)})

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.available is False
    assert status.reason == "Could not query MPRIS media players."


def test_player_status_failure_has_no_track() -> None:
    responses = playing_responses()
    responses[("playerctl", "-p", "spotifast", "status")] = completed([], "", 1)

    status = PlayerctlMprisProvider(runner=Runner(responses)).now_playing()

    assert status.available is True
    assert status.track is None
    assert status.reason == "The media player is not responding."


def test_missing_title_has_no_track() -> None:
    responses = playing_responses(title="")
    status = PlayerctlMprisProvider(runner=Runner(responses)).now_playing()

    assert status.track is None
    assert status.reason == "The media player has no track metadata."


def test_track_url_is_used_when_track_id_is_missing() -> None:
    responses = playing_responses(track_id="")
    responses[("playerctl", "-p", "spotifast", "metadata", "xesam:url")] = completed(
        [], "spotify:track:url-fallback"
    )

    status = PlayerctlMprisProvider(runner=Runner(responses)).now_playing()

    assert status.track is not None
    assert status.track.track_id == "spotify:track:url-fallback"


def test_environment_override_skips_detection(monkeypatch) -> None:
    monkeypatch.setenv("SPOTUI_MPRIS_PLAYER", "spotify")
    responses = playing_responses(player="spotify")
    runner = Runner(responses)

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.player == "spotify"
    assert runner.calls[0][0] == ["playerctl", "-p", "spotify", "status"]


def test_first_player_is_used_when_no_spotify_client_matches() -> None:
    responses = {
        ("playerctl", "-l"): completed([], "mpv\nvlc\n"),
        ("playerctl", "-p", "mpv", "status"): completed([], "Playing"),
        ("playerctl", "-p", "mpv", "metadata", "xesam:title"): completed([], "Song"),
        ("playerctl", "-p", "mpv", "metadata", "xesam:artist"): completed([], "Artist"),
        ("playerctl", "-p", "mpv", "metadata", "mpris:trackid"): completed([], ""),
        ("playerctl", "-p", "mpv", "metadata", "xesam:url"): completed([], ""),
    }

    status = PlayerctlMprisProvider(runner=Runner(responses)).now_playing()

    assert status.player == "mpv"
    assert status.track is not None
    assert status.track.track_id is None


@pytest.mark.parametrize("error", [OSError("no session")])
def test_os_failure_is_unavailable(error: Exception) -> None:
    runner = Runner({("playerctl", "-l"): error})

    status = PlayerctlMprisProvider(runner=runner).now_playing()

    assert status.available is False
    assert status.reason == "MPRIS is unavailable."
