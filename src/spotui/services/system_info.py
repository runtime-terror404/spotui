"""Read-only application information for the Settings screen."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from spotui import __version__
from spotui.paths import Paths

Runner = Callable[..., subprocess.CompletedProcess[str]]
_MUSIC_DIRECTORY_RE = re.compile(r"(?m)^Music\s*:\s*(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class SystemInfo:
    version: str
    root: str
    config_file: str
    download_directory: str | None
    downloader_available: bool


def parse_music_directory(output: str) -> str | None:
    match = _MUSIC_DIRECTORY_RE.search(output)
    return match.group(1).strip() if match else None


class SystemInfoService:
    """Expose safe paths and read the downloader's configured destination."""

    def __init__(
        self,
        paths: Paths,
        *,
        runner: Runner = subprocess.run,
    ) -> None:
        self._paths = paths
        self._runner = runner

    def info(self) -> SystemInfo:
        executable = self._paths.lucidadl_executable
        available = executable.is_file() and os.access(executable, os.X_OK)
        directory = self._music_directory(executable) if available else None
        return SystemInfo(
            version=__version__,
            root=str(self._paths.data_dir),
            config_file=str(self._paths.config_file),
            download_directory=directory,
            downloader_available=available,
        )

    def _music_directory(self, executable: Path) -> str | None:
        try:
            result = self._runner(
                [str(executable), "config"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return parse_music_directory(result.stdout or "")


__all__ = [
    "SystemInfo",
    "SystemInfoService",
    "parse_music_directory",
]
