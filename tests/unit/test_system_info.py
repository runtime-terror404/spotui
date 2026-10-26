from __future__ import annotations

import subprocess

from spotui import __version__
from spotui.services.system_info import SystemInfoService, parse_music_directory


def test_parse_music_directory() -> None:
    output = (
        "Music       : /mnt/Shared/Music\n"
        "Data        : /home/user/.local/share/lucidadl\n"
    )

    assert parse_music_directory(output) == "/mnt/Shared/Music"
    assert parse_music_directory("Data : /tmp\n") is None


def test_system_info_reports_paths_and_missing_downloader(env) -> None:
    info = SystemInfoService(env.paths).info()

    assert info.version == __version__
    assert info.root == str(env.paths.data_dir)
    assert info.config_file == str(env.paths.config_file)
    assert info.download_directory is None
    assert info.downloader_available is False


def test_system_info_reads_the_downloader_music_directory(env) -> None:
    executable = env.paths.lucidadl_executable
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    commands: list[list[str]] = []

    def runner(command, **_kwargs):  # noqa: ANN001, ANN202
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "Music       : /mnt/Shared/Music\nData : /tmp/lucidadl\n",
            "",
        )

    info = SystemInfoService(env.paths, runner=runner).info()

    assert commands == [[str(executable), "config"]]
    assert info.downloader_available is True
    assert info.download_directory == "/mnt/Shared/Music"


def test_downloader_config_failure_is_non_fatal(env) -> None:
    executable = env.paths.lucidadl_executable
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)

    def failing_runner(command, **_kwargs):  # noqa: ANN001, ANN202
        return subprocess.CompletedProcess(command, 1, "", "boom")

    info = SystemInfoService(env.paths, runner=failing_runner).info()

    assert info.downloader_available is True
    assert info.download_directory is None
