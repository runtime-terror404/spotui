from __future__ import annotations

import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest

from spotui import __version__
from spotui.cli import main
from spotui.deps import CheckStatus, DependencyCheck, DependencyReport
from spotui.lifecycle import ProcessLock, inspect_lock
from spotui.persistence.migrate import (
    current_revision,
    head_revision,
    upgrade_database,
)
from spotui.server import Listener
from tests.helpers import write_config


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])

    assert caught.value.code == 0
    assert f"spotui {__version__}" in capsys.readouterr().out


def test_db_upgrade_and_current(env, capsys) -> None:
    assert main(["db", "upgrade"]) == 0
    output = capsys.readouterr().out
    assert "Database is current" in output
    assert current_revision(f"sqlite:///{env.paths.database_file}") == head_revision()

    assert main(["db", "current"]) == 0
    current_output = capsys.readouterr().out
    assert head_revision() in current_output
    assert "(head)" in current_output


def test_db_current_before_initialization(env, capsys) -> None:
    assert main(["db", "current"]) == 0

    output = capsys.readouterr().out
    assert "not initialized" in output
    assert not env.paths.database_file.exists()


def test_db_upgrade_is_idempotent(env) -> None:
    assert main(["db", "upgrade"]) == 0
    assert main(["db", "upgrade"]) == 0


def test_invalid_config_fails_before_startup(env, capsys) -> None:
    write_config(env.paths, "[server]\nport = 0\n")

    assert main(["serve"]) == 1

    error = capsys.readouterr().err
    assert "spotui:" in error
    assert "port" in error


def test_serve_requires_migrations(env, capsys) -> None:
    port = free_port()

    assert main(["serve", "--port", str(port)]) == 1

    error = capsys.readouterr().err
    assert "spotui db upgrade" in error
    assert inspect_lock(env.paths.lock_file).locked is False


def test_serve_reports_port_collision(env, capsys, migrated_database_url: str) -> None:
    port = free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", port))
        blocker.listen(1)

        assert main(["serve", "--port", str(port)]) == 1

    error = capsys.readouterr().err
    assert f"127.0.0.1:{port}" in error
    assert "cannot listen" in error
    assert inspect_lock(env.paths.lock_file).locked is False


def test_serve_reports_existing_instance(env, capsys) -> None:
    lock = ProcessLock(env.paths.lock_file)
    lock.acquire({"urls": ["http://127.0.0.1:8765"], "pid": 1234})
    try:
        assert main(["serve", "--port", str(free_port())]) == 1
    finally:
        lock.release()

    error = capsys.readouterr().err
    assert "already running" in error
    assert "http://127.0.0.1:8765" in error


def test_status_reports_effective_state(env, capsys) -> None:
    port = free_port()

    assert main(["status", "--port", str(port)]) == 0

    output = capsys.readouterr().out
    assert f"SpotUI {__version__}" in output
    assert f"http://127.0.0.1:{port}" in output
    assert "LAN: disabled" in output
    assert f"Launcher: {env.paths.launcher_file} (not installed)" in output
    assert f"Systemd unit: {env.paths.systemd_unit_file} (not installed)" in output
    assert "Server: not running" in output
    assert "Health: unreachable" in output


def test_status_reports_locked_server(env, capsys) -> None:
    lock = ProcessLock(env.paths.lock_file)
    lock.acquire({"urls": ["http://127.0.0.1:8765"]})
    try:
        assert main(["status", "--port", str(free_port())]) == 0
    finally:
        lock.release()

    output = capsys.readouterr().out
    assert "Server: running" in output
    assert f"pid {os.getpid()}" in output


def test_status_reports_lan_plan(env, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "spotui.cli.listener_specs",
        lambda config: (
            Listener(kind="local", host="127.0.0.1", port=config.server.port),
            Listener(kind="lan", host="192.168.1.20", port=config.server.port),
        ),
    )
    write_config(env.paths, '[server]\ntrusted_subnet = "192.168.1.0/24"\n')

    assert main(["status", "--port", str(free_port())]) == 0

    output = capsys.readouterr().out
    assert "LAN: http://192.168.1.20:" in output
    assert "192.168.1.0/24" in output


def test_deps_check_missing_environment(env, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "spotui.cli.check_spotui_browser",
        lambda: DependencyReport(
            (DependencyCheck("SpotUI Playwright", CheckStatus.OK, "ok"),)
        ),
    )

    assert main(["deps", "check"]) == 1

    output = capsys.readouterr().out
    assert "missing" in output
    assert "deps install" in output
    assert "SpotUI browser runtime" in output


def test_deps_install_dispatches(env, capsys, monkeypatch) -> None:
    calls: list[Path] = []
    browser_calls: list[bool] = []
    monkeypatch.setattr("spotui.cli.install_downloader", lambda paths: calls.append(paths))
    monkeypatch.setattr(
        "spotui.cli.install_spotui_browser",
        lambda: browser_calls.append(True),
    )
    monkeypatch.setattr(
        "spotui.cli.check_downloader",
        lambda paths: DependencyReport(
            (DependencyCheck("managed environment", CheckStatus.OK, str(paths.lucidadl_env_dir)),)
        ),
    )
    monkeypatch.setattr(
        "spotui.cli.check_spotui_browser",
        lambda: DependencyReport(
            (DependencyCheck("SpotUI Playwright", CheckStatus.OK, "ok"),)
        ),
    )

    assert main(["deps", "install"]) == 0

    assert calls == [env.paths]
    assert browser_calls == [True]
    output = capsys.readouterr().out
    assert "Installing" in output
    assert "SpotUI's Playwright Chromium" in output


def test_deps_upgrade_dispatches(env, capsys, monkeypatch) -> None:
    monkeypatch.setattr("spotui.cli.install_downloader", lambda paths: None)
    monkeypatch.setattr("spotui.cli.install_spotui_browser", lambda: None)
    monkeypatch.setattr(
        "spotui.cli.check_downloader",
        lambda paths: DependencyReport(
            (DependencyCheck("managed environment", CheckStatus.OK, "ok"),)
        ),
    )
    monkeypatch.setattr(
        "spotui.cli.check_spotui_browser",
        lambda: DependencyReport(
            (DependencyCheck("SpotUI Playwright", CheckStatus.OK, "ok"),)
        ),
    )

    assert main(["deps", "upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Upgrading" in output


def test_db_upgrade_backs_up_existing_database(env, capsys) -> None:
    env.paths.ensure_runtime_directories()
    database_url = f"sqlite:///{env.paths.database_file}"
    upgrade_database(database_url, "0005_paired_devices")

    assert main(["db", "upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Backup before migration:" in output
    assert current_revision(database_url) == head_revision()
    backups = list(env.paths.backup_dir.glob("spotui-*.sqlite3"))
    assert len(backups) == 1


def test_db_backup_command(env, capsys, migrated_database_url: str) -> None:
    target = env.root / "manual-backup.sqlite3"

    assert main(["db", "backup", "--output", str(target)]) == 0

    assert target.is_file()
    assert f"Backup: {target}" in capsys.readouterr().out
    with sqlite3.connect(target) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def _write_legacy_queue(env) -> Path:
    legacy_path = env.paths.legacy_queue_file
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    jobs = [
        {
            "id": "legacy01",
            "title": "Queued song",
            "artist": "Artist",
            "url": "https://music.amazon.com/tracks/B000000001",
            "status": "queued",
            "message": "queued",
            "file": "",
            "added": 1_700_000_000,
            "updated": 1_700_000_000,
        },
        {
            "id": "legacy02",
            "title": "Running song",
            "artist": "Artist",
            "url": "https://music.amazon.com/tracks/B000000002",
            "status": "downloading",
            "message": "downloading…",
            "file": "",
            "added": 1_700_000_000,
            "updated": 1_700_000_100,
        },
    ]
    legacy_path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return legacy_path


def _legacy_job_states(env) -> list[tuple[str, str]]:
    with sqlite3.connect(env.paths.database_file) as connection:
        return connection.execute(
            "SELECT title, state FROM download_jobs ORDER BY title"
        ).fetchall()


def test_migrate_legacy_dry_run_and_confirmation(
    env, capsys, monkeypatch, migrated_database_url: str
) -> None:
    legacy_path = _write_legacy_queue(env)
    original = legacy_path.read_bytes()

    assert main(["migrate-legacy", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "Dry run" in output
    assert "imported: 2" in output
    assert _legacy_job_states(env) == []

    assert main(["migrate-legacy"]) == 1

    assert "refusing to write without --yes" in capsys.readouterr().err
    assert _legacy_job_states(env) == []

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "nope")

    assert main(["migrate-legacy"]) == 1

    assert "migration cancelled" in capsys.readouterr().out
    assert _legacy_job_states(env) == []
    assert legacy_path.read_bytes() == original


def test_migrate_legacy_is_repeat_safe(env, capsys, migrated_database_url: str) -> None:
    legacy_path = _write_legacy_queue(env)
    original = legacy_path.read_bytes()

    assert main(["migrate-legacy", "--yes"]) == 0

    first_output = capsys.readouterr().out
    assert "imported: 2" in first_output
    assert _legacy_job_states(env) == [
        ("Queued song", "queued"),
        ("Running song", "interrupted"),
    ]

    assert main(["migrate-legacy", "--yes"]) == 0

    second_output = capsys.readouterr().out
    assert "imported: 0" in second_output
    assert "skipped: 2" in second_output
    assert legacy_path.read_bytes() == original
    assert _legacy_job_states(env) == [
        ("Queued song", "queued"),
        ("Running song", "interrupted"),
    ]


def test_migrate_legacy_requires_migrated_database(env, capsys) -> None:
    _write_legacy_queue(env)

    assert main(["migrate-legacy", "--dry-run"]) == 1

    assert "spotui db upgrade" in capsys.readouterr().err


def test_service_commands_dispatch(env, capsys, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "spotui.cli.install_service",
        lambda paths, executable=None, daemon_reload=True: (
            calls.append(f"install:{executable}:{daemon_reload}")
            or paths.systemd_unit_file
        ),
    )
    monkeypatch.setattr("spotui.cli.enable_service", lambda: calls.append("enable"))
    monkeypatch.setattr("spotui.cli.disable_service", lambda: calls.append("disable"))
    monkeypatch.setattr(
        "spotui.cli.uninstall_service",
        lambda paths: calls.append("uninstall") or True,
    )
    monkeypatch.setattr("spotui.cli.service_status", lambda: "active")
    executable = Path("/opt/SpotUI/bin/spotui")

    assert (
        main(
            [
                "service",
                "install",
                "--exec",
                str(executable),
                "--no-daemon-reload",
            ]
        )
        == 0
    )
    assert main(["service", "enable"]) == 0
    assert main(["service", "disable"]) == 0
    assert main(["service", "uninstall"]) == 0
    assert main(["service", "status"]) == 0

    assert calls == [
        f"install:{executable}:False",
        "enable",
        "disable",
        "uninstall",
    ]
    output = capsys.readouterr().out
    assert "spotui.service: active" in output
