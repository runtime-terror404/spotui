from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotui.service import (
    ServiceError,
    disable_service,
    enable_service,
    install_service,
    render_service_unit,
    resolve_service_executable,
    service_environment,
    service_status,
    uninstall_service,
)


def fake_runner(calls: list[Sequence[str]]):
    def run(command, **_kwargs):  # noqa: ANN001, ANN202
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, "active\n", "")

    return run


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_unit_uses_the_installed_executable(env) -> None:
    managed = executable(env.paths.spotui_env_dir / "bin" / "spotui")

    resolved = resolve_service_executable(env.paths)

    assert resolved == managed.resolve()
    unit = render_service_unit(resolved)
    assert f'ExecStart="{managed.resolve()}" serve' in unit
    assert "WantedBy=default.target" in unit
    assert "Restart=on-failure" in unit
    assert "StartLimitBurst=5" in unit


def test_unit_quotes_paths_with_spaces_and_percent_signs() -> None:
    unit = render_service_unit(Path("/home/me/Spot UI %/spotui"))

    assert 'ExecStart="/home/me/Spot UI %%/spotui" serve' in unit


def test_missing_managed_executable_is_actionable(env) -> None:
    with pytest.raises(ServiceError, match="run the installer or pass --exec"):
        resolve_service_executable(env.paths)


def test_install_is_idempotent_and_does_not_enable(env) -> None:
    managed = executable(env.paths.spotui_env_dir / "bin" / "spotui")
    calls: list[Sequence[str]] = []

    first = install_service(env.paths, executable=managed, runner=fake_runner(calls))
    contents = first.read_text(encoding="utf-8")
    second = install_service(env.paths, executable=managed, runner=fake_runner(calls))

    assert first == second == env.paths.systemd_unit_file
    assert second.read_text(encoding="utf-8") == contents
    assert f'Environment="SPOTUI_HOME={env.paths.data_dir}"' in contents
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "daemon-reload"],
    ]
    assert os.stat(second).st_mode & 0o777 == 0o644


def test_service_environment_pins_the_root_and_default_config(env) -> None:
    env.paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    env.paths.config_file.write_text("", encoding="utf-8")

    environment = service_environment(env.paths)

    assert environment == {"SPOTUI_HOME": str(env.paths.data_dir)}


def test_service_environment_pins_a_custom_config_path(env) -> None:
    custom = env.root / "custom-spotui.toml"
    custom.write_text("", encoding="utf-8")
    paths = replace(env.paths, config_file=custom)

    environment = service_environment(paths)

    assert environment == {
        "SPOTUI_HOME": str(paths.data_dir),
        "SPOTUI_CONFIG": str(custom),
    }


def test_enable_disable_and_status_use_user_systemctl(env) -> None:
    calls: list[Sequence[str]] = []
    runner = fake_runner(calls)

    enable_service(runner=runner)
    disable_service(runner=runner)
    status = service_status(runner=runner)

    assert status == "active"
    assert calls == [
        ["systemctl", "--user", "enable", "--now", "spotui.service"],
        ["systemctl", "--user", "disable", "--now", "spotui.service"],
        ["systemctl", "--user", "is-active", "spotui.service"],
    ]


def test_uninstall_removes_only_the_unit(env) -> None:
    managed = executable(env.paths.spotui_env_dir / "bin" / "spotui")
    install_service(env.paths, executable=managed, runner=fake_runner([]))
    data_file = env.paths.data_dir / "spotui.sqlite3"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("data", encoding="utf-8")
    calls: list[Sequence[str]] = []

    existed = uninstall_service(env.paths, runner=fake_runner(calls))

    assert existed is True
    assert not env.paths.systemd_unit_file.exists()
    assert data_file.read_text(encoding="utf-8") == "data"
    assert calls == [
        ["systemctl", "--user", "disable", "--now", "spotui.service"],
        ["systemctl", "--user", "daemon-reload"],
    ]


def test_uninstall_is_idempotent_without_a_unit(env) -> None:
    existed = uninstall_service(env.paths, runner=fake_runner([]))

    assert existed is False


def test_install_fails_when_daemon_reload_fails(env) -> None:
    managed = executable(env.paths.spotui_env_dir / "bin" / "spotui")

    def failing_runner(command, **_kwargs):  # noqa: ANN001, ANN202
        return SimpleNamespace(returncode=1, stdout="", stderr="bus unavailable")

    with pytest.raises(ServiceError, match="bus unavailable"):
        install_service(env.paths, executable=managed, runner=failing_runner)
