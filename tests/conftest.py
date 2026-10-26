from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from spotui.config import AppConfig, load_config
from spotui.logging_setup import reset_logging
from spotui.paths import Paths
from spotui.persistence.database import database_url_for_path
from spotui.persistence.migrate import upgrade_database


@dataclass(slots=True)
class XdgEnvironment:
    root: Path
    home: Path
    config_home: Path
    data_home: Path
    state_home: Path
    cache_home: Path
    runtime_home: Path
    paths: Paths
    config: AppConfig


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> XdgEnvironment:
    """Give every test an isolated XDG home and deterministic config."""
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    state_home = tmp_path / "state"
    cache_home = tmp_path / "cache"
    runtime_home = tmp_path / "run"
    for directory in (home, config_home, data_home, state_home, cache_home, runtime_home):
        directory.mkdir(parents=True, exist_ok=True)

    values = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "XDG_STATE_HOME": str(state_home),
        "XDG_CACHE_HOME": str(cache_home),
        "XDG_RUNTIME_DIR": str(runtime_home),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in (
        "XDG_BIN_HOME",
        "SPOTUI_CONFIG",
        "SPOTUI_PORT",
        "SPOTUI_TRUSTED_SUBNET",
        "SPOTUI_SHUTDOWN_GRACE_SECONDS",
        "SPOTUI_LOG_LEVEL",
        "SPOTUI_LOG_MAX_BYTES",
        "SPOTUI_LOG_BACKUP_COUNT",
        "SPOTUI_CANCEL_GRACE_SECONDS",
        "SPOTUI_QUEUE_SHUTDOWN_GRACE_SECONDS",
        "SPOTUI_JOB_TIMEOUT_SECONDS",
        "SPOTUI_MPRIS_PLAYER",
        "SPOTGRAB_PLAYER",
        "SPOTUI_LIBRARY_ROOTS",
        "SPOTUI_LIBRARY_REFRESH_SECONDS",
        "SPOTUI_LIBRARY_SCAN_ON_STARTUP",
        "SPOTUI_MATCHING_CONCURRENCY",
    ):
        monkeypatch.delenv(key, raising=False)

    paths = Paths.resolve()
    return XdgEnvironment(
        root=tmp_path,
        home=home,
        config_home=config_home,
        data_home=data_home,
        state_home=state_home,
        cache_home=cache_home,
        runtime_home=runtime_home,
        paths=paths,
        config=load_config(paths),
    )


@pytest.fixture(autouse=True)
def _reset_spotui_logging():
    reset_logging()
    yield
    reset_logging()


@pytest.fixture
def env(isolated_xdg: XdgEnvironment) -> XdgEnvironment:
    return isolated_xdg


@pytest.fixture
def database_url(env: XdgEnvironment) -> str:
    env.paths.ensure_runtime_directories()
    return database_url_for_path(env.paths.database_file)


@pytest.fixture
def migrated_database_url(database_url: str) -> str:
    upgrade_database(database_url)
    return database_url
