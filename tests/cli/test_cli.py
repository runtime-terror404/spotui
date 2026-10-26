from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from spotui import __version__
from spotui.cli import main
from spotui.deps import CheckStatus, DependencyCheck, DependencyReport
from spotui.lifecycle import ProcessLock, inspect_lock
from spotui.persistence.migrate import current_revision, head_revision
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


def test_deps_check_missing_environment(env, capsys) -> None:
    assert main(["deps", "check"]) == 1

    output = capsys.readouterr().out
    assert "missing" in output
    assert "deps install" in output


def test_deps_install_dispatches(env, capsys, monkeypatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr("spotui.cli.install_downloader", lambda paths: calls.append(paths))
    monkeypatch.setattr(
        "spotui.cli.check_downloader",
        lambda paths: DependencyReport(
            (DependencyCheck("managed environment", CheckStatus.OK, str(paths.lucidadl_env_dir)),)
        ),
    )

    assert main(["deps", "install"]) == 0

    assert calls == [env.paths]
    output = capsys.readouterr().out
    assert "Installing" in output


def test_deps_upgrade_dispatches(env, capsys, monkeypatch) -> None:
    monkeypatch.setattr("spotui.cli.install_downloader", lambda paths: None)
    monkeypatch.setattr(
        "spotui.cli.check_downloader",
        lambda paths: DependencyReport(
            (DependencyCheck("managed environment", CheckStatus.OK, "ok"),)
        ),
    )

    assert main(["deps", "upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Upgrading" in output
