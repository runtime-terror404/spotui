from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2 as httpx

from spotui.lifecycle import inspect_lock


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(process: subprocess.Popen[str], base_url: str) -> httpx.Response:
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            raise AssertionError(
                f"server exited with {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
        try:
            response = httpx.get(f"{base_url}/api/v1/health", timeout=1.0)
            if response.status_code == 200:
                return response
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.1)
    raise AssertionError(f"server did not become healthy: {last_error}")


def stop_server(process: subprocess.Popen[str]) -> tuple[str, str]:
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
        raise AssertionError(
            f"server did not stop gracefully\nstdout:\n{stdout}\nstderr:\n{stderr}"
        ) from exc
    return stdout, stderr


def test_foreground_server_lifecycle(env, migrated_database_url: str) -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()

    process = subprocess.Popen(
        [sys.executable, "-m", "spotui", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        health = wait_for_health(process, base_url)
        body = health.json()
        assert body["ok"] is True
        assert health.headers["x-request-id"]

        root = httpx.get(f"{base_url}/", timeout=2.0)
        assert root.status_code == 200
        assert "SpotUI" in root.text

        assert inspect_lock(env.paths.lock_file).locked is True
        metadata = inspect_lock(env.paths.lock_file).metadata
        assert metadata is not None
        assert metadata["urls"] == [base_url]
        assert metadata["pid"] == process.pid

        second = subprocess.run(
            [sys.executable, "-m", "spotui", "serve", "--port", str(port)],
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
        assert second.returncode == 1
        assert "already running" in second.stderr
        assert base_url in second.stderr

        stdout, stderr = stop_server(process)
        assert process.returncode in (0, -signal.SIGTERM), (
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
        assert inspect_lock(env.paths.lock_file).locked is False
        log_text = env.paths.log_file.read_text(encoding="utf-8")
        assert "SpotUI stopped" in log_text
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_restart_after_shutdown_reuses_port_and_lock(
    env, migrated_database_url: str
) -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()

    for _ in range(2):
        process = subprocess.Popen(
            [sys.executable, "-m", "spotui", "serve", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        try:
            wait_for_health(process, base_url)
        finally:
            if process.poll() is None:
                stop_server(process)
        assert process.returncode in (0, -signal.SIGTERM)
        assert inspect_lock(env.paths.lock_file).locked is False


def test_serve_without_migrations_exits_with_instruction(env) -> None:
    port = free_port()
    environment = os.environ.copy()

    result = subprocess.run(
        [sys.executable, "-m", "spotui", "serve", "--port", str(port)],
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )

    assert result.returncode == 1
    assert "spotui db upgrade" in result.stderr
    assert inspect_lock(env.paths.lock_file).locked is False


def test_lock_metadata_is_json(env, migrated_database_url: str) -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "spotui", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    try:
        wait_for_health(process, base_url)
        metadata = json.loads(Path(env.paths.lock_file).read_text(encoding="utf-8"))
        assert metadata["urls"] == [base_url]
    finally:
        if process.poll() is None:
            stop_server(process)
