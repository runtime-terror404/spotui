"""Managed lucidadl subprocess adapter.

The adapter owns exactly the process it starts, parses only documented phase
and summary lines, keeps bounded diagnostic state, and never deletes partial
media output.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("spotui.downloader.lucidadl")

_PHASE_RE = re.compile(r"^\s*…\s+(.+)$")
_TALLY_RE = re.compile(r"Done\s*[—-]\s*OK:(\d+)\s+skipped:(\d+)\s+failed:(\d+)")
_OUTPUT_RE = re.compile(r"✓\s+(.+?)\s+\([\d.]+ MB\)")


class DownloadOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DownloadPhase:
    name: str
    message: str
    percent: float | None = None


@dataclass(frozen=True, slots=True)
class DownloadResult:
    outcome: DownloadOutcome
    message: str
    output_path: str | None = None
    error: str | None = None
    exit_code: int | None = None


class Downloader(Protocol):
    def available(self) -> bool: ...

    def run(
        self,
        url: str,
        on_phase: Callable[[DownloadPhase], None],
    ) -> DownloadResult: ...

    def cancel_active(self, grace_seconds: float) -> None: ...


def build_command(executable: Path, watchlist_file: str) -> list[str]:
    return [
        str(executable),
        "tracks",
        "-f",
        watchlist_file,
        "-s",
        "amazon",
        "-j",
        "1",
        "--hidden",
    ]


def parse_phase(line: str) -> DownloadPhase | None:
    match = _PHASE_RE.match(line)
    if not match:
        return None
    text = match.group(1).strip()
    if "Downloading stream" in text:
        return DownloadPhase("downloading", "downloading…")
    if "Ripping" in text:
        return DownloadPhase("ripping", "ripping…")
    if "Fetching" in text:
        return DownloadPhase("fetching", "fetching metadata…")
    if "Fixing" in text:
        return DownloadPhase("finalizing", "finalizing…")
    if "stuck" in text or "retrying" in text:
        return DownloadPhase("downloading", "stalled — retrying…")
    return None


def parse_tally(line: str) -> tuple[int, int, int] | None:
    match = _TALLY_RE.search(line)
    if not match:
        return None
    ok, skipped, failed = (int(value) for value in match.groups())
    return ok, skipped, failed


def parse_output_path(line: str) -> str | None:
    match = _OUTPUT_RE.search(line)
    return match.group(1).strip() if match else None


class LucidadlDownloader:
    def __init__(self, executable: Path) -> None:
        self._executable = executable
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False
        self._force_timer: threading.Timer | None = None

    def available(self) -> bool:
        return self._executable.is_file() and os.access(self._executable, os.X_OK)

    def run(
        self,
        url: str,
        on_phase: Callable[[DownloadPhase], None],
    ) -> DownloadResult:
        with self._lock:
            if self._cancel_requested:
                self._cancel_requested = False
                return DownloadResult(DownloadOutcome.CANCELLED, "cancelled")

        watchlist = tempfile.NamedTemporaryFile(
            "w",
            suffix=".txt",
            prefix="spotui-",
            delete=False,
            encoding="utf-8",
        )
        command = build_command(self._executable, watchlist.name)
        process: subprocess.Popen[str] | None = None
        tally: tuple[int, int, int] | None = None
        output_path: str | None = None
        try:
            watchlist.write(url + "\n")
            watchlist.close()
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
            with self._lock:
                self._process = process
                cancelled_before_read = self._cancel_requested
            if cancelled_before_read:
                self._signal_process(process, signal.SIGTERM)

            assert process.stdout is not None
            for line in process.stdout:
                phase = parse_phase(line)
                if phase is not None:
                    try:
                        on_phase(phase)
                    except Exception:
                        logger.exception("failed to persist downloader phase")
                    continue
                parsed_tally = parse_tally(line)
                if parsed_tally is not None:
                    tally = parsed_tally
                    continue
                parsed_output = parse_output_path(line)
                if parsed_output is not None:
                    output_path = parsed_output

            returncode = process.wait()
            with self._lock:
                cancelled = self._cancel_requested
            if cancelled:
                return DownloadResult(
                    DownloadOutcome.CANCELLED,
                    "cancelled",
                    exit_code=returncode,
                )

            if tally is None:
                return DownloadResult(
                    DownloadOutcome.FAILED,
                    "download failed",
                    error="The downloader finished without a success summary.",
                    exit_code=returncode,
                )
            ok, skipped, failed = tally
            if failed == 0 and (ok > 0 or skipped > 0):
                already = ok == 0 and skipped > 0
                return DownloadResult(
                    DownloadOutcome.COMPLETED,
                    "already in library" if already else "saved",
                    output_path=output_path,
                    exit_code=returncode,
                )
            return DownloadResult(
                DownloadOutcome.FAILED,
                "download failed",
                error="The downloader reported a failed track.",
                exit_code=returncode,
            )
        finally:
            with self._lock:
                timer, self._force_timer = self._force_timer, None
                self._process = None
                self._cancel_requested = False
            if timer is not None:
                timer.cancel()
            if process is not None and process.poll() is None:
                self._signal_process(process, signal.SIGKILL)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.error("downloader subprocess did not exit after forced termination")
            Path(watchlist.name).unlink(missing_ok=True)

    def cancel_active(self, grace_seconds: float) -> None:
        with self._lock:
            self._cancel_requested = True
            process = self._process
            if process is None:
                return
            self._signal_process(process, signal.SIGTERM)
            timer = threading.Timer(
                max(0.0, grace_seconds),
                self._force_terminate,
                args=(process,),
            )
            timer.daemon = True
            previous, self._force_timer = self._force_timer, timer
            if previous is not None:
                previous.cancel()
            timer.start()

    @staticmethod
    def _signal_process(process: subprocess.Popen[str], sig: int) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except OSError:
            logger.warning("failed to signal the owned downloader process group")

    @staticmethod
    def _force_terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            LucidadlDownloader._signal_process(process, signal.SIGKILL)
