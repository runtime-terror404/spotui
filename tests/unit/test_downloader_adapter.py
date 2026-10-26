from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from spotui.providers.downloader.lucidadl import (
    DownloadOutcome,
    DownloadPhase,
    LucidadlDownloader,
    build_command,
    parse_output_path,
    parse_phase,
    parse_tally,
)


def write_script(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_parsers_match_documented_output() -> None:
    assert parse_phase("  … Ripping track…") == DownloadPhase("ripping", "ripping…")
    assert parse_phase("  … Downloading stream for x to add metadata") == DownloadPhase(
        "downloading", "downloading…"
    )
    assert parse_phase("  … Fetching metadata…") == DownloadPhase(
        "fetching", "fetching metadata…"
    )
    assert parse_phase("  … Fixing tags…") == DownloadPhase(
        "finalizing", "finalizing…"
    )
    assert parse_phase("  … stuck (>40s without progress)") == DownloadPhase(
        "downloading", "stalled — retrying…"
    )
    assert parse_phase("random progress bar") is None
    assert parse_tally("Done — OK:2  skipped:0  failed:0") == (2, 0, 0)
    assert parse_tally("Done — OK:0  skipped:1  failed:0") == (0, 1, 0)
    assert parse_tally("Done — OK:0  skipped:0  failed:1") == (0, 0, 1)
    assert parse_tally("no tally") is None
    assert parse_output_path("✓ Artist/Album/Song.flac (43.6 MB)") == (
        "Artist/Album/Song.flac"
    )


def test_build_command_is_an_argument_list(tmp_path: Path) -> None:
    command = build_command(tmp_path / "lucida", "/tmp/watchlist.txt")

    assert command == [
        str(tmp_path / "lucida"),
        "tracks",
        "-f",
        "/tmp/watchlist.txt",
        "-s",
        "amazon",
        "-j",
        "1",
        "--hidden",
    ]


def test_success_parses_phases_and_tally(tmp_path: Path, monkeypatch) -> None:
    args_file = tmp_path / "args.txt"
    monkeypatch.setenv("SPOTUI_ARGS_FILE", str(args_file))
    executable = write_script(
        tmp_path,
        "lucida",
        """
import os, sys
with open(os.environ["SPOTUI_ARGS_FILE"], "w") as fh:
    fh.write("\\n".join(sys.argv))
print("  … Fetching metadata…", flush=True)
print("  … Ripping track…", flush=True)
print("  … Downloading stream for Track to add metadata", flush=True)
print("  … Fixing tags…", flush=True)
print("✓ Artist/Album/Song.flac (43.6 MB)", flush=True)
print("Done — OK:1  skipped:0  failed:0", flush=True)
""",
    )
    downloader = LucidadlDownloader(executable)
    phases: list[DownloadPhase] = []

    result = downloader.run("https://music.amazon.com/tracks/B002TRACK1", phases.append)

    assert result.outcome is DownloadOutcome.COMPLETED
    assert result.message == "saved"
    assert result.output_path == "Artist/Album/Song.flac"
    assert result.exit_code == 0
    assert [phase.name for phase in phases] == [
        "fetching",
        "ripping",
        "downloading",
        "finalizing",
    ]
    recorded = args_file.read_text().splitlines()
    assert recorded[1] == "tracks"
    watchlist = Path(recorded[3])
    assert not watchlist.exists()


def test_already_downloaded_skip_is_completed(tmp_path: Path) -> None:
    executable = write_script(
        tmp_path,
        "lucida",
        """
print("  ⏭ already downloaded / in progress, skipped: Song", flush=True)
print("Done — OK:0  skipped:1  failed:0", flush=True)
""",
    )

    result = LucidadlDownloader(executable).run(
        "https://music.amazon.com/tracks/B002TRACK1",
        lambda phase: None,
    )

    assert result.outcome is DownloadOutcome.COMPLETED
    assert result.message == "already in library"
    assert result.output_path is None


def test_not_found_skip_is_failed(tmp_path: Path) -> None:
    executable = write_script(
        tmp_path,
        "lucida",
        """
print("  ⃠ not found, skipped: https://music.amazon.com/tracks/B002TRACK1", flush=True)
print("Done — OK:0  skipped:1  failed:0", flush=True)
""",
    )

    result = LucidadlDownloader(executable).run(
        "https://music.amazon.com/tracks/B002TRACK1",
        lambda phase: None,
    )

    assert result.outcome is DownloadOutcome.FAILED
    assert "could not find a downloadable track" in (result.error or "")


def test_unexplained_skip_is_failed(tmp_path: Path) -> None:
    executable = write_script(
        tmp_path,
        "lucida",
        """
print("Done — OK:0  skipped:1  failed:0", flush=True)
""",
    )

    result = LucidadlDownloader(executable).run(
        "https://music.amazon.com/tracks/B002TRACK1",
        lambda phase: None,
    )

    assert result.outcome is DownloadOutcome.FAILED
    assert "without confirming an existing download" in (result.error or "")


@pytest.mark.parametrize(
    ("tally", "error"),
    [
        ("Done — OK:0  skipped:0  failed:1", "failed track"),
        ("no summary", "success summary"),
    ],
)
def test_failed_or_missing_tally_is_failed(
    tmp_path: Path, tally: str, error: str
) -> None:
    executable = write_script(
        tmp_path,
        "lucida",
        f'print({tally!r}, flush=True)\n',
    )

    result = LucidadlDownloader(executable).run(
        "https://music.amazon.com/tracks/B002TRACK1",
        lambda phase: None,
    )

    assert result.outcome is DownloadOutcome.FAILED
    assert error in (result.error or "")


def test_missing_executable_is_unavailable(tmp_path: Path) -> None:
    assert LucidadlDownloader(tmp_path / "missing").available() is False


def test_cancellation_terminates_only_owned_process_group(
    tmp_path: Path, monkeypatch
) -> None:
    executable = write_script(
        tmp_path,
        "lucida",
        """
import time
print("  … Downloading stream for Track to add metadata", flush=True)
time.sleep(30)
print("Done — OK:1  skipped:0  failed:0", flush=True)
""",
    )
    unrelated = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        downloader = LucidadlDownloader(executable)
        started = threading.Event()

        def on_phase(phase: DownloadPhase) -> None:
            if phase.name == "downloading":
                started.set()

        results = []
        thread = threading.Thread(
            target=lambda: results.append(
                downloader.run(
                    "https://music.amazon.com/tracks/B002TRACK1",
                    on_phase,
                )
            )
        )
        thread.start()
        assert started.wait(5)
        downloader.cancel_active(0.2)
        thread.join(10)

        assert not thread.is_alive()
        assert results[0].outcome is DownloadOutcome.CANCELLED
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=10)
