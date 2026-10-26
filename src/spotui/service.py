"""Optional systemd user-service helpers for installed SpotUI."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from spotui.paths import Paths

SERVICE_NAME = "spotui.service"
Runner = Callable[..., subprocess.CompletedProcess[str]]


class ServiceError(RuntimeError):
    """A systemd user-service operation could not be completed."""


def resolve_service_executable(
    paths: Paths,
    explicit: Path | str | None = None,
) -> Path:
    """Resolve a stable executable path, preferring the installed environment."""
    if explicit is not None:
        candidate = Path(explicit).expanduser()
    else:
        candidate = paths.spotui_env_dir / "bin" / "spotui"
        if not candidate.is_file():
            raise ServiceError(
                "installed SpotUI executable not found at "
                f"{candidate}; run the installer or pass --exec"
            )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ServiceError(f"spotui executable not found: {candidate}") from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ServiceError(f"spotui executable is not runnable: {resolved}")
    return resolved


def _systemd_command(path: Path) -> str:
    escaped = (
        str(path)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _systemd_environment(name: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'Environment="{name}={escaped}"'


def render_service_unit(
    executable: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> str:
    environment_lines = ["Environment=PYTHONUNBUFFERED=1"]
    environment_lines.extend(
        _systemd_environment(name, value)
        for name, value in sorted((environment or {}).items())
    )
    environment_block = "\n".join(environment_lines)
    return (
        "[Unit]\n"
        "Description=SpotUI local music search and download server\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "StartLimitIntervalSec=60\n"
        "StartLimitBurst=5\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={_systemd_command(executable)} serve\n"
        f"{environment_block}\n"
        "UMask=0077\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "TimeoutStopSec=30\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def service_environment(paths: Paths) -> dict[str, str]:
    """Pin the installed application root and any non-default config path."""
    environment = {"SPOTUI_HOME": str(paths.data_dir)}
    default_config = paths.config_dir / "config.toml"
    if paths.config_file != default_config and paths.config_file.is_file():
        environment["SPOTUI_CONFIG"] = str(paths.config_file)
    return environment


def _run_systemctl(
    args: Sequence[str],
    *,
    runner: Runner,
    required: bool,
) -> subprocess.CompletedProcess[str] | None:
    command = ["systemctl", "--user", *args]
    try:
        result = runner(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        if required:
            raise ServiceError(f"systemctl --user {args[0]} failed: {exc}") from exc
        return None
    if result.returncode != 0 and required:
        detail = (result.stderr or result.stdout or "").strip()
        raise ServiceError(
            f"systemctl --user {args[0]} failed"
            + (f": {detail[:300]}" if detail else "")
        )
    return result


def install_service(
    paths: Paths,
    *,
    executable: Path | str | None = None,
    runner: Runner = subprocess.run,
    daemon_reload: bool = True,
) -> Path:
    """Write or refresh the user unit; this does not enable or start it."""
    resolved = resolve_service_executable(paths, executable)
    unit_path = paths.systemd_unit_file
    try:
        unit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        contents = render_service_unit(
            resolved,
            environment=service_environment(paths),
        )
        temporary = unit_path.with_suffix(".tmp")
        temporary.write_text(contents, encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, unit_path)
    except OSError as exc:
        raise ServiceError(f"cannot write systemd unit {unit_path}: {exc}") from exc
    if daemon_reload:
        _run_systemctl(["daemon-reload"], runner=runner, required=True)
    return unit_path


def enable_service(
    runner: Runner = subprocess.run,
) -> None:
    _run_systemctl(["enable", "--now", SERVICE_NAME], runner=runner, required=True)


def disable_service(
    runner: Runner = subprocess.run,
) -> None:
    _run_systemctl(["disable", "--now", SERVICE_NAME], runner=runner, required=True)


def uninstall_service(
    paths: Paths,
    *,
    runner: Runner = subprocess.run,
) -> bool:
    """Stop/disable a unit if present and remove only the unit file."""
    existed = paths.systemd_unit_file.exists()
    _run_systemctl(["disable", "--now", SERVICE_NAME], runner=runner, required=False)
    try:
        paths.systemd_unit_file.unlink(missing_ok=True)
    except OSError as exc:
        raise ServiceError(
            f"cannot remove systemd unit {paths.systemd_unit_file}: {exc}"
        ) from exc
    _run_systemctl(["daemon-reload"], runner=runner, required=False)
    return existed


def service_status(
    runner: Runner = subprocess.run,
) -> str:
    result = _run_systemctl(["is-active", SERVICE_NAME], runner=runner, required=False)
    if result is None:
        return "unavailable"
    return (result.stdout or result.stderr or "unknown").strip() or "unknown"


__all__ = [
    "SERVICE_NAME",
    "ServiceError",
    "disable_service",
    "enable_service",
    "install_service",
    "render_service_unit",
    "resolve_service_executable",
    "service_environment",
    "service_status",
    "uninstall_service",
]
