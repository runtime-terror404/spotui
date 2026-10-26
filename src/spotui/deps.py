"""Managed downloader dependency checks and explicit installation.

The application never installs or upgrades anything at startup. These
functions back the ``spotui deps check``, ``deps install``, and ``deps upgrade``
commands only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from spotui.logging_setup import redact_text
from spotui.paths import Paths

# Pinned from the 2026-10-26 capability audit (lucidadl 1.0.0). Revisit only
# through the release process after Phase 4 captures real downloader output.
SUPPORTED_LUCIDADL_VERSION = "1.0.0"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class DependencyError(RuntimeError):
    """A required dependency is missing or a dependency command failed."""


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    status: CheckStatus
    detail: str
    remedy: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyReport:
    checks: tuple[DependencyCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status is not CheckStatus.FAIL for check in self.checks)


def _run(
    runner: Runner, command: Sequence[str], timeout: float = 20.0
) -> subprocess.CompletedProcess[str]:
    return runner(list(command), capture_output=True, text=True, timeout=timeout)


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _failure_detail(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout or "").strip()
    return redact_text(output)[:200] if output else f"exit status {result.returncode}"


def _parse_lucidadl_version(output: str) -> str | None:
    match = re.search(r"lucidadl\s+(\d+\.\d+\.\d+)", output)
    return match.group(1) if match else None


def _parse_clearance_path(output: str) -> Path | None:
    match = re.search(r"(?m)^Data\s*:\s*(.+)$", output)
    if not match:
        return None
    return Path(match.group(1).strip()).expanduser() / "clearance.json"


def check_downloader(paths: Paths, *, runner: Runner = subprocess.run) -> DependencyReport:
    """Check the managed lucidadl environment without changing anything."""
    checks: list[DependencyCheck] = []
    env_dir = paths.lucidadl_env_dir
    env_exists = env_dir.is_dir()
    checks.append(
        DependencyCheck(
            "managed environment",
            CheckStatus.OK if env_exists else CheckStatus.FAIL,
            str(env_dir) if env_exists else f"missing: {env_dir}",
            None if env_exists else "run 'spotui deps install'",
        )
    )
    python_ok = _executable(paths.lucidadl_python)
    checks.append(
        DependencyCheck(
            "environment Python",
            CheckStatus.OK if python_ok else CheckStatus.FAIL,
            str(paths.lucidadl_python) if python_ok else "missing or not executable",
            None if python_ok else "run 'spotui deps install'",
        )
    )
    lucida_ok = _executable(paths.lucidadl_executable)
    checks.append(
        DependencyCheck(
            "lucida executable",
            CheckStatus.OK if lucida_ok else CheckStatus.FAIL,
            str(paths.lucidadl_executable) if lucida_ok else "missing or not executable",
            None if lucida_ok else "run 'spotui deps install'",
        )
    )
    if not (python_ok and lucida_ok):
        return DependencyReport(tuple(checks))

    try:
        version_result = _run(runner, [str(paths.lucidadl_executable), "--version"])
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(
            DependencyCheck(
                "lucidadl version",
                CheckStatus.FAIL,
                redact_text(str(exc))[:200],
                "run 'spotui deps install'",
            )
        )
    else:
        if version_result.returncode != 0:
            checks.append(
                DependencyCheck(
                    "lucidadl version",
                    CheckStatus.FAIL,
                    _failure_detail(version_result),
                    "run 'spotui deps install'",
                )
            )
        else:
            installed = _parse_lucidadl_version(
                f"{version_result.stdout}\n{version_result.stderr}"
            )
            if installed is None:
                checks.append(
                    DependencyCheck(
                        "lucidadl version",
                        CheckStatus.FAIL,
                        "could not determine version from 'lucida --version'",
                        "run 'spotui deps install'",
                    )
                )
            elif installed != SUPPORTED_LUCIDADL_VERSION:
                checks.append(
                    DependencyCheck(
                        "lucidadl version",
                        CheckStatus.FAIL,
                        f"installed {installed}, pinned {SUPPORTED_LUCIDADL_VERSION}",
                        "run 'spotui deps upgrade'",
                    )
                )
            else:
                checks.append(
                    DependencyCheck(
                        "lucidadl version",
                        CheckStatus.OK,
                        f"{installed} (pinned)",
                    )
                )

    playwright_ok = False
    try:
        playwright_result = _run(
            runner,
            [str(paths.lucidadl_python), "-m", "playwright", "--version"],
        )
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(
            DependencyCheck(
                "Playwright package",
                CheckStatus.FAIL,
                redact_text(str(exc))[:200],
                "run 'spotui deps install'",
            )
        )
    else:
        playwright_ok = playwright_result.returncode == 0
        checks.append(
            DependencyCheck(
                "Playwright package",
                CheckStatus.OK if playwright_ok else CheckStatus.FAIL,
                (playwright_result.stdout or "").strip() or _failure_detail(playwright_result),
                None if playwright_ok else "run 'spotui deps install'",
            )
        )

    if playwright_ok:
        _check_browser_artifacts(paths, runner, checks)

    try:
        config_result = _run(runner, [str(paths.lucidadl_executable), "config"])
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(
            DependencyCheck(
                "Cloudflare setup",
                CheckStatus.WARNING,
                f"could not inspect lucidadl configuration: {redact_text(str(exc))[:160]}",
                f"run '{paths.lucidadl_executable} setup' in a desktop session",
            )
        )
    else:
        clearance_path = (
            _parse_clearance_path(config_result.stdout)
            if config_result.returncode == 0
            else None
        )
        if clearance_path is None:
            checks.append(
                DependencyCheck(
                    "Cloudflare setup",
                    CheckStatus.WARNING,
                    "could not determine the lucidadl data directory",
                    f"run '{paths.lucidadl_executable} setup' in a desktop session",
                )
            )
        elif clearance_path.is_file():
            checks.append(
                DependencyCheck(
                    "Cloudflare setup",
                    CheckStatus.OK,
                    "cached clearance present",
                )
            )
        else:
            checks.append(
                DependencyCheck(
                    "Cloudflare setup",
                    CheckStatus.WARNING,
                    "no cached Cloudflare clearance",
                    f"run '{paths.lucidadl_executable} setup' in a desktop session",
                )
            )

    return DependencyReport(tuple(checks))


def _check_browser_artifacts(
    paths: Paths, runner: Runner, checks: list[DependencyCheck]
) -> None:
    try:
        result = _run(
            runner,
            [
                str(paths.lucidadl_python),
                "-m",
                "playwright",
                "install",
                "--dry-run",
                "chromium",
            ],
            timeout=30.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(
            DependencyCheck(
                "Chromium browser",
                CheckStatus.FAIL,
                redact_text(str(exc))[:200],
                "run 'spotui deps install'",
            )
        )
        return
    if result.returncode != 0:
        checks.append(
            DependencyCheck(
                "Chromium browser",
                CheckStatus.FAIL,
                _failure_detail(result),
                "run 'spotui deps install'",
            )
        )
        return

    locations = [
        Path(value.strip())
        for value in re.findall(r"Install location:\s*(.+)", result.stdout or "")
    ]
    if not locations:
        checks.append(
            DependencyCheck(
                "Chromium browser",
                CheckStatus.WARNING,
                "Playwright did not report browser install locations",
                "run 'spotui deps install'",
            )
        )
        return
    missing = [location for location in locations if not location.exists()]
    if missing:
        checks.append(
            DependencyCheck(
                "Chromium browser",
                CheckStatus.FAIL,
                f"missing browser artifact(s): {', '.join(str(path) for path in missing)}",
                "run 'spotui deps install'",
            )
        )
    else:
        checks.append(
            DependencyCheck(
                "Chromium browser",
                CheckStatus.OK,
                f"{len(locations)} Playwright artifact(s) present",
            )
        )


def install_commands(paths: Paths, uv_executable: str) -> list[list[str]]:
    """Commands that create/update the managed environment with the pin."""
    return [
        [uv_executable, "venv", "--allow-existing", str(paths.lucidadl_env_dir)],
        [
            uv_executable,
            "pip",
            "install",
            "--python",
            str(paths.lucidadl_python),
            f"lucidadl=={SUPPORTED_LUCIDADL_VERSION}",
        ],
        [str(paths.lucidadl_python), "-m", "playwright", "install", "chromium"],
    ]


def find_uv() -> str | None:
    return shutil.which("uv")


def install_downloader(
    paths: Paths,
    *,
    uv_executable: str | None = None,
    runner: Runner = subprocess.run,
) -> None:
    """Install or reconcile the managed lucidadl environment to the pin.

    Called only by an explicit CLI command. Browser installation is included,
    but the interactive ``lucida setup`` Cloudflare step is never automated.
    """
    uv = uv_executable or find_uv()
    if not uv:
        raise DependencyError(
            "uv was not found on PATH; install uv before running 'spotui deps install'"
        )
    paths.ensure_runtime_directories()
    for command in install_commands(paths, uv):
        try:
            result = runner(command)
        except (OSError, subprocess.SubprocessError) as exc:
            raise DependencyError(
                f"dependency command failed: {redact_text(str(exc))[:200]}"
            ) from exc
        if result.returncode != 0:
            raise DependencyError(
                f"dependency command failed with status {result.returncode}: "
                f"{' '.join(command[:4])} ..."
            )


def report_lines(report: DependencyReport) -> list[str]:
    lines = []
    labels = {
        CheckStatus.OK: "ok",
        CheckStatus.WARNING: "warn",
        CheckStatus.FAIL: "fail",
    }
    for check in report.checks:
        line = f"[{labels[check.status]:4}] {check.name}: {check.detail}"
        if check.remedy and check.status is not CheckStatus.OK:
            line += f"\n       fix: {check.remedy}"
        lines.append(line)
    return lines


__all__ = [
    "CheckStatus",
    "DependencyCheck",
    "DependencyError",
    "DependencyReport",
    "Runner",
    "SUPPORTED_LUCIDADL_VERSION",
    "check_downloader",
    "find_uv",
    "install_commands",
    "install_downloader",
    "report_lines",
]
