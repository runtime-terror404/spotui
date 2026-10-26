from __future__ import annotations

from pathlib import Path

import pytest

from spotui.paths import PathError, Paths


def test_all_application_data_lives_under_one_root(env) -> None:
    paths = env.paths
    root = env.data_home / "spotui"

    assert paths.data_dir == root
    assert paths.config_dir == root
    assert paths.config_file == root / "config.toml"
    assert paths.database_file == root / "spotui.sqlite3"
    assert paths.backup_dir == root / "backups"
    assert paths.legacy_queue_file == root / "queue.json"
    assert paths.log_dir == root / "logs"
    assert paths.log_file == root / "logs" / "spotui.log"
    assert paths.cache_dir == root / "cache"
    assert paths.runtime_dir == root / "run"
    assert paths.lock_file.parent == root / "run"
    assert paths.lock_file.name.startswith("server-")
    assert paths.spotui_env_dir == root / "envs" / "spotui"
    assert paths.lucidadl_env_dir == root / "envs" / "lucidadl"
    assert paths.lucidadl_executable == paths.lucidadl_env_dir / "bin" / "lucida"
    assert paths.lucidadl_python == paths.lucidadl_env_dir / "bin" / "python"


def test_launcher_and_systemd_unit_are_the_only_integration_paths(env) -> None:
    paths = env.paths

    assert paths.bin_dir == env.bin_home
    assert paths.launcher_file == env.bin_home / "spotui"
    assert paths.systemd_unit_file == (
        env.config_home / "systemd" / "user" / "spotui.service"
    )


def test_relative_xdg_values_are_ignored(tmp_path: Path) -> None:
    environ = {
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": "relative/data",
        "XDG_CONFIG_HOME": "relative/config",
        "XDG_BIN_HOME": "relative/bin",
    }

    paths = Paths.resolve(environ=environ)

    root = tmp_path / "home" / ".local" / "share" / "spotui"
    assert paths.data_dir == root
    assert paths.config_file == root / "config.toml"
    assert paths.cache_dir == root / "cache"
    assert paths.runtime_dir == root / "run"
    assert paths.systemd_unit_file == (
        tmp_path / "home" / ".config" / "systemd" / "user" / "spotui.service"
    )
    assert paths.launcher_file == tmp_path / "home" / ".local" / "bin" / "spotui"


def test_spotui_home_relocates_the_complete_root(tmp_path: Path) -> None:
    root = tmp_path / "portable-spotui"
    environ = {
        "HOME": str(tmp_path),
        "XDG_DATA_HOME": str(tmp_path / "ignored-data"),
        "XDG_CONFIG_HOME": str(tmp_path / "ignored-config"),
        "SPOTUI_HOME": str(root),
    }

    paths = Paths.resolve(environ=environ)

    assert paths.data_dir == root
    assert paths.config_file == root / "config.toml"
    assert paths.database_file == root / "spotui.sqlite3"
    assert paths.log_file == root / "logs" / "spotui.log"
    assert paths.cache_dir == root / "cache"
    assert paths.runtime_dir == root / "run"
    assert paths.spotui_env_dir == root / "envs" / "spotui"


@pytest.mark.parametrize(
    "root",
    ["relative/spotui", "/"],
)
def test_unsafe_spotui_home_is_rejected(root: str) -> None:
    environ = {"HOME": "/home/test-user", "SPOTUI_HOME": root}

    with pytest.raises(PathError, match="SPOTUI_HOME"):
        Paths.resolve(environ=environ)


def test_spotui_home_cannot_be_the_home_directory(tmp_path: Path) -> None:
    environ = {"HOME": str(tmp_path), "SPOTUI_HOME": str(tmp_path)}

    with pytest.raises(PathError, match="dedicated directory"):
        Paths.resolve(environ=environ)


def test_explicit_config_path_wins(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.toml"
    environ = {"HOME": str(tmp_path), "SPOTUI_CONFIG": str(tmp_path / "env.toml")}

    paths = Paths.resolve(config_file=explicit, environ=environ)

    assert paths.config_file == explicit
    assert paths.config_dir == tmp_path / ".local" / "share" / "spotui"


def test_spotui_config_environment_is_used(tmp_path: Path) -> None:
    configured = tmp_path / "env.toml"
    paths = Paths.resolve(environ={"HOME": str(tmp_path), "SPOTUI_CONFIG": str(configured)})

    assert paths.config_file == configured


def test_lock_is_keyed_by_root_directory(tmp_path: Path) -> None:
    first = Paths.resolve(environ={"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "a")})
    second = Paths.resolve(environ={"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "b")})

    assert first.lock_file.parent == first.data_dir / "run"
    assert second.lock_file.parent == second.data_dir / "run"
    assert first.lock_file != second.lock_file


def test_ensure_runtime_directories(env) -> None:
    env.paths.ensure_runtime_directories()

    for directory in (
        env.paths.data_dir,
        env.paths.cache_dir,
        env.paths.runtime_dir,
        env.paths.log_dir,
    ):
        assert directory.is_dir()
