"""Filesystem layout for SpotUI.

All application-owned persistent data lives under one root so users have a
single directory to inspect, back up, or remove. The default root is the XDG
data directory for SpotUI (``~/.local/share/spotui``); ``SPOTUI_HOME`` can
override it with another absolute path.

The PATH launcher and the optional systemd user unit are the only integration
points outside the root because the operating system requires fixed locations
for them.
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
    """All application-owned paths for one user and root directory."""

    config_file: Path
    config_dir: Path
    data_dir: Path
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
        """Resolve the single application root and integration paths.

        Precedence for the configuration file is the CLI ``--config`` option,
        then ``SPOTUI_CONFIG``, then ``<root>/config.toml``. All other
        application-owned paths are derived from ``<root>``. Set
        ``SPOTUI_HOME`` to relocate the root; otherwise ``XDG_DATA_HOME``
        selects its parent.
        """
        env = os.environ if environ is None else environ
        home = Path(env.get("HOME", str(Path.home())))
        data_home = _xdg_dir(env, "XDG_DATA_HOME", home / ".local" / "share")
        bin_home = _xdg_dir(env, "XDG_BIN_HOME", home / ".local" / "bin")

        root_override = env.get("SPOTUI_HOME", "").strip()
        if root_override:
            root = Path(root_override).expanduser()
            if not root.is_absolute():
                raise PathError("SPOTUI_HOME must be an absolute path")
            if root == Path(root.anchor) or root == home:
                raise PathError("SPOTUI_HOME must be a dedicated directory")
        else:
            root = data_home / APP_NAME

        config_dir = root
        if config_file is not None:
            resolved_config = config_file.expanduser()
        elif env.get("SPOTUI_CONFIG", "").strip():
            resolved_config = Path(env["SPOTUI_CONFIG"]).expanduser()
        else:
            resolved_config = config_dir / "config.toml"

        cache_dir = root / "cache"
        runtime_dir = root / "run"
        log_dir = root / "logs"

        # One server per root, even when multiple roots are used by the same
        # user. The OS lock lives inside the root; stale files are harmless
        # because lock ownership comes from the kernel, not file existence.
        digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        lock_file = runtime_dir / f"server-{digest}.lock"

        lucidadl_env_dir = root / "envs" / "lucidadl"
        return cls(
            config_file=resolved_config,
            config_dir=config_dir,
            data_dir=root,
            cache_dir=cache_dir,
            runtime_dir=runtime_dir,
            database_file=root / "spotui.sqlite3",
            backup_dir=root / "backups",
            legacy_queue_file=root / "queue.json",
            log_dir=log_dir,
            log_file=log_dir / "spotui.log",
            lock_file=lock_file,
            bin_dir=bin_home,
            launcher_file=bin_home / APP_NAME,
            systemd_unit_file=(
                _xdg_dir(env, "XDG_CONFIG_HOME", home / ".config")
                / "systemd"
                / "user"
                / f"{APP_NAME}.service"
            ),
            spotui_env_dir=root / "envs" / "spotui",
            lucidadl_env_dir=lucidadl_env_dir,
            lucidadl_executable=lucidadl_env_dir / "bin" / "lucida",
            lucidadl_python=lucidadl_env_dir / "bin" / "python",
        )

    def ensure_runtime_directories(self) -> None:
        """Create the writable application directories with user-only access."""
        for directory in (
            self.data_dir,
            self.cache_dir,
            self.runtime_dir,
            self.log_dir,
        ):
            try:
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            except OSError as exc:
                raise PathError(f"cannot create directory {directory}: {exc}") from exc
