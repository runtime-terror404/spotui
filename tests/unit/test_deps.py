from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from spotui.deps import (
    SUPPORTED_LUCIDADL_VERSION,
    CheckStatus,
    DependencyError,
    check_downloader,
    install_commands,
    install_downloader,
)


@dataclass
class FakeRunner:
    responses: dict[tuple[str, ...], Any]
    calls: list[list[str]] | None = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(command))
        response = self.responses.get(tuple(command))
        if isinstance(response, Exception):
            raise response
        if response is not None:
            return response
        return subprocess.CompletedProcess(command, 0, "", "")


def completed(
    command: list[str], stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def prepare_environment(env) -> tuple[Path, Path]:
    paths = env.paths
    paths.lucidadl_python.parent.mkdir(parents=True, exist_ok=True)
    for executable in (paths.lucidadl_python, paths.lucidadl_executable):
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)

    browser = env.root / "browsers" / "chromium-1234"
    browser.mkdir(parents=True)
    lucidadl_data = env.root / "lucidadl-data"
    lucidadl_data.mkdir(parents=True)
    (lucidadl_data / "clearance.json").write_text("{}", encoding="utf-8")
    return browser, lucidadl_data


def healthy_runner(env) -> tuple[FakeRunner, Path]:
    browser, lucidadl_data = prepare_environment(env)
    paths = env.paths
    responses = {
        (str(paths.lucidadl_executable), "--version"): completed(
            [], f"lucidadl {SUPPORTED_LUCIDADL_VERSION}\n"
        ),
        (str(paths.lucidadl_python), "-m", "playwright", "--version"): completed(
            [], "Version 1.62.0\n"
        ),
        (
            str(paths.lucidadl_python),
            "-m",
            "playwright",
            "install",
            "--dry-run",
            "chromium",
        ): completed([], f"Install location:    {browser}\n"),
        (str(paths.lucidadl_executable), "config"): completed(
            [], f"Data        : {lucidadl_data}\n"
        ),
    }
    return FakeRunner(responses), browser


def test_healthy_environment(env) -> None:
    runner, _browser = healthy_runner(env)

    report = check_downloader(env.paths, runner=runner)

    assert report.ok is True
    assert all(check.status is CheckStatus.OK for check in report.checks)
    names = [check.name for check in report.checks]
    assert names == [
        "managed environment",
        "environment Python",
        "lucida executable",
        "lucidadl version",
        "Playwright package",
        "Chromium browser",
        "Cloudflare setup",
    ]


def test_missing_environment_fails_with_install_remedy(env) -> None:
    report = check_downloader(env.paths, runner=FakeRunner({}))

    assert report.ok is False
    assert report.checks[0].status is CheckStatus.FAIL
    assert "deps install" in (report.checks[0].remedy or "")


def test_version_mismatch_fails_with_upgrade_remedy(env) -> None:
    runner, _ = healthy_runner(env)
    runner.responses[(str(env.paths.lucidadl_executable), "--version")] = completed(
        [], "lucidadl 0.9.0\n"
    )

    report = check_downloader(env.paths, runner=runner)

    version_check = next(check for check in report.checks if check.name == "lucidadl version")
    assert version_check.status is CheckStatus.FAIL
    assert "deps upgrade" in (version_check.remedy or "")


def test_missing_browser_artifact_fails(env) -> None:
    runner, browser = healthy_runner(env)
    browser.rmdir()
    runner.responses[
        (
            str(env.paths.lucidadl_python),
            "-m",
            "playwright",
            "install",
            "--dry-run",
            "chromium",
        )
    ] = completed([], f"Install location:    {browser}\n")

    report = check_downloader(env.paths, runner=runner)

    browser_check = next(check for check in report.checks if check.name == "Chromium browser")
    assert browser_check.status is CheckStatus.FAIL


def test_missing_clearance_is_only_a_warning(env) -> None:
    runner, _ = healthy_runner(env)
    (env.root / "lucidadl-data" / "clearance.json").unlink()

    report = check_downloader(env.paths, runner=runner)

    clearance_check = next(
        check for check in report.checks if check.name == "Cloudflare setup"
    )
    assert clearance_check.status is CheckStatus.WARNING
    assert "setup" in (clearance_check.remedy or "")
    assert report.ok is True


def test_command_failure_is_reported(env) -> None:
    runner, _ = healthy_runner(env)
    runner.responses[(str(env.paths.lucidadl_executable), "--version")] = completed(
        [], "", returncode=2, stderr="boom"
    )

    report = check_downloader(env.paths, runner=runner)

    version_check = next(check for check in report.checks if check.name == "lucidadl version")
    assert version_check.status is CheckStatus.FAIL
    assert "boom" in version_check.detail


def test_install_commands_are_argument_lists_with_the_pin(env) -> None:
    commands = install_commands(env.paths, "/usr/bin/uv")

    assert commands == [
        ["/usr/bin/uv", "venv", "--allow-existing", str(env.paths.lucidadl_env_dir)],
        [
            "/usr/bin/uv",
            "pip",
            "install",
            "--python",
            str(env.paths.lucidadl_python),
            f"lucidadl=={SUPPORTED_LUCIDADL_VERSION}",
        ],
        [
            str(env.paths.lucidadl_python),
            "-m",
            "playwright",
            "install",
            "chromium",
        ],
    ]
    assert all(isinstance(command, list) for command in commands)


def test_install_downloader_runs_commands_without_shell(env) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    install_downloader(env.paths, uv_executable="/usr/bin/uv", runner=runner)

    assert calls == install_commands(env.paths, "/usr/bin/uv")


def test_install_downloader_reports_failed_command(env) -> None:
    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "network down")

    with pytest.raises(DependencyError, match="status 1"):
        install_downloader(env.paths, uv_executable="/usr/bin/uv", runner=runner)


def test_install_downloader_requires_uv(env, monkeypatch) -> None:
    monkeypatch.setattr("spotui.deps.find_uv", lambda: None)

    with pytest.raises(DependencyError, match="uv"):
        install_downloader(env.paths, runner=FakeRunner({}))


def test_spotui_browser_check_ok(tmp_path, monkeypatch) -> None:
    import spotui.deps as deps

    browser = tmp_path / "chromium-1234"
    browser.mkdir()
    monkeypatch.setattr(deps.metadata, "version", lambda name: "1.64.1")

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, f"Install location:    {browser}\n", ""
        )

    report = deps.check_spotui_browser(
        python_executable=tmp_path / "python",
        runner=runner,
    )

    assert report.ok is True
    assert [check.name for check in report.checks] == [
        "SpotUI Playwright",
        "SpotUI Chromium",
    ]
    assert all(check.status is CheckStatus.OK for check in report.checks)


def test_spotui_browser_missing_package(monkeypatch) -> None:
    import spotui.deps as deps

    def missing(name: str):
        raise deps.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(deps.metadata, "version", missing)

    report = deps.check_spotui_browser(runner=FakeRunner({}))

    assert report.ok is False
    assert report.checks[0].name == "SpotUI Playwright"
    assert "uv sync" in (report.checks[0].remedy or "")


def test_spotui_browser_missing_artifact(tmp_path, monkeypatch) -> None:
    import spotui.deps as deps

    monkeypatch.setattr(deps.metadata, "version", lambda name: "1.64.1")
    missing = tmp_path / "chromium-missing"

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, f"Install location:    {missing}\n", ""
        )

    report = deps.check_spotui_browser(
        python_executable=tmp_path / "python",
        runner=runner,
    )

    assert report.ok is False
    assert report.checks[1].name == "SpotUI Chromium"
    assert report.checks[1].status is CheckStatus.FAIL


def test_spotui_browser_install_runs_or_raises(tmp_path) -> None:
    from spotui.deps import (
        DependencyError,
        install_spotui_browser,
        spotui_browser_install_command,
    )

    python = tmp_path / "python"
    command = spotui_browser_install_command(python)
    assert command == [str(python), "-m", "playwright", "install", "chromium"]

    calls: list[list[str]] = []

    def ok(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    install_spotui_browser(python_executable=python, runner=ok)
    assert calls == [command]

    def failed(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "failed")

    with pytest.raises(DependencyError, match="status 1"):
        install_spotui_browser(python_executable=python, runner=failed)
