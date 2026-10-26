"""XDG path resolution for SpotUI.

Every filesystem location used by the application is derived here so that no
other module has to guess at ``~/.local``, the current working directory, or
the location of managed environments.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "spotui"


class PathError(RuntimeError):
    """Raised when a required SpotUI directory cannot be created or used."""


def _xdg_dir(environ: Mapping[str, str], variable: str, fallback: Path) -> Path:
    """Return an absolute XDG variable when valid, otherwise *fallback*."""
    raw = environ.get(variable, "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            return candidate
    return fallback


@dataclass(frozen=True, slots=True)
class Paths:
    """All application-owned paths for one user and data directory."""

    config_file: Path
    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path
    runtime_dir: Path
    database_file: Path
    backup_dir: Path
    legacy_queue_file: Path
    log_dir: Path
    log_file: Path
    lock_file: Path
    bin_dir: Path
    launcher_file: Path
    systemd_unit_file: Path
    spotui_env_dir: Path
    lucidadl_env_dir: Path
    lucidadl_executable: Path
    lucidadl_python: Path

    @classmethod
    def resolve(
        cls,
        *,
        config_file: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> Paths:
        """Resolve paths from XDG variables and SpotUI deployment overrides.

        ``config_file`` (from the CLI) has precedence over ``SPOTUI_CONFIG``,
        which has precedence over the default XDG location.
        """
        env = os.environ if environ is None else environ
        home = Path(env.get("HOME", str(Path.home())))

        config_home = _xdg_dir(env, "XDG_CONFIG_HOME", home / ".config")
        data_home = _xdg_dir(env, "XDG_DATA_HOME", home / ".local" / "share")
        state_home = _xdg_dir(env, "XDG_STATE_HOME", home / ".local" / "state")
        cache_home = _xdg_dir(env, "XDG_CACHE_HOME", home / ".cache")
        bin_home = _xdg_dir(env, "XDG_BIN_HOME", home / ".local" / "bin")

        config_dir = config_home / APP_NAME
        if config_file is not None:
            resolved_config = config_file.expanduser()
        elif env.get("SPOTUI_CONFIG", "").strip():
            resolved_config = Path(env["SPOTUI_CONFIG"]).expanduser()
        else:
            resolved_config = config_dir / "config.toml"

        data_dir = data_home / APP_NAME
        state_dir = state_home / APP_NAME
        cache_dir = cache_home / APP_NAME

        # XDG_RUNTIME_DIR is the correct home for locks and ephemeral sockets.
        # When it is unavailable, keep them in the per-user state directory.
        runtime_dir = _xdg_dir(env, "XDG_RUNTIME_DIR", state_dir / "run") / APP_NAME

        # One server per data directory, even when several data directories are
        # used by the same user. The OS lock itself lives in the runtime dir.
        digest = hashlib.sha256(str(data_dir.resolve()).encode()).hexdigest()[:16]
        lock_file = runtime_dir / f"server-{digest}.lock"

        lucidadl_env_dir = data_dir / "envs" / "lucidadl"
        return cls(
            config_file=resolved_config,
            config_dir=config_dir,
            data_dir=data_dir,
            state_dir=state_dir,
            cache_dir=cache_dir,
            runtime_dir=runtime_dir,
            database_file=data_dir / "spotui.sqlite3",
            backup_dir=data_dir / "backups",
            legacy_queue_file=data_dir / "queue.json",
            log_dir=state_dir / "logs",
            log_file=state_dir / "logs" / "spotui.log",
            lock_file=lock_file,
            bin_dir=bin_home,
            launcher_file=bin_home / APP_NAME,
            systemd_unit_file=config_home / "systemd" / "user" / f"{APP_NAME}.service",
            spotui_env_dir=data_dir / "envs" / "spotui",
            lucidadl_env_dir=lucidadl_env_dir,
            lucidadl_executable=lucidadl_env_dir / "bin" / "lucida",
            lucidadl_python=lucidadl_env_dir / "bin" / "python",
        )

    def ensure_runtime_directories(self) -> None:
        """Create the writable application directories with user-only access."""
        for directory in (
            self.data_dir,
            self.state_dir,
            self.cache_dir,
            self.runtime_dir,
            self.log_dir,
        ):
            try:
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            except OSError as exc:
                raise PathError(f"cannot create directory {directory}: {exc}") from exc
