from __future__ import annotations

from pathlib import Path

from spotui.paths import Paths


def test_xdg_directories_are_respected(env) -> None:
    paths = env.paths

    assert paths.config_file == env.config_home / "spotui" / "config.toml"
    assert paths.config_dir == env.config_home / "spotui"
    assert paths.data_dir == env.data_home / "spotui"
    assert paths.state_dir == env.state_home / "spotui"
    assert paths.cache_dir == env.cache_home / "spotui"
    assert paths.runtime_dir == env.runtime_home / "spotui"
    assert paths.database_file == paths.data_dir / "spotui.sqlite3"
    assert paths.backup_dir == paths.data_dir / "backups"
    assert paths.legacy_queue_file == paths.data_dir / "queue.json"
    assert paths.log_file == paths.state_dir / "logs" / "spotui.log"
    assert paths.bin_dir == env.home / ".local" / "bin"
    assert paths.launcher_file == paths.bin_dir / "spotui"
    assert paths.systemd_unit_file == (
        env.config_home / "systemd" / "user" / "spotui.service"
    )
    assert paths.spotui_env_dir == paths.data_dir / "envs" / "spotui"
    assert paths.lucidadl_env_dir == paths.data_dir / "envs" / "lucidadl"
    assert paths.lucidadl_executable == paths.lucidadl_env_dir / "bin" / "lucida"
    assert paths.lucidadl_python == paths.lucidadl_env_dir / "bin" / "python"


def test_relative_xdg_values_are_ignored(tmp_path: Path) -> None:
    environ = {
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": "relative/data",
        "XDG_STATE_HOME": "relative/state",
        "XDG_CACHE_HOME": "relative/cache",
        "XDG_CONFIG_HOME": "relative/config",
        "XDG_RUNTIME_DIR": "relative/run",
    }

    paths = Paths.resolve(environ=environ)

    assert paths.data_dir == tmp_path / "home" / ".local" / "share" / "spotui"
    assert paths.state_dir == tmp_path / "home" / ".local" / "state" / "spotui"
    assert paths.cache_dir == tmp_path / "home" / ".cache" / "spotui"
    assert paths.config_file == tmp_path / "home" / ".config" / "spotui" / "config.toml"
    assert paths.runtime_dir == paths.state_dir / "run" / "spotui"


def test_explicit_config_path_wins(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.toml"
    environ = {"HOME": str(tmp_path), "SPOTUI_CONFIG": str(tmp_path / "env.toml")}

    paths = Paths.resolve(config_file=explicit, environ=environ)

    assert paths.config_file == explicit


def test_spotui_config_environment_is_used(tmp_path: Path) -> None:
    configured = tmp_path / "env.toml"
    paths = Paths.resolve(environ={"HOME": str(tmp_path), "SPOTUI_CONFIG": str(configured)})

    assert paths.config_file == configured


def test_lock_is_keyed_by_data_directory(tmp_path: Path) -> None:
    first = Paths.resolve(environ={"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "a")})
    second = Paths.resolve(environ={"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "b")})

    assert first.lock_file.parent == second.lock_file.parent
    assert first.lock_file != second.lock_file


def test_ensure_runtime_directories(env) -> None:
    env.paths.ensure_runtime_directories()

    for directory in (
        env.paths.data_dir,
        env.paths.state_dir,
        env.paths.cache_dir,
        env.paths.runtime_dir,
        env.paths.log_dir,
    ):
        assert directory.is_dir()
