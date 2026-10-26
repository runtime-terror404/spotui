from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from spotui.domain.catalog import CatalogKind
from spotui.domain.errors import (
    CatalogResponseError,
    CatalogTimeoutError,
    CatalogUnavailableError,
)
from spotui.providers.amazon.lucida import LucidaDetailProvider


class Runner:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fake_python(tmp_path: Path) -> Path:
    executable = tmp_path / "python"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def provider(tmp_path: Path, runner: Runner) -> LucidaDetailProvider:
    script = tmp_path / "bridge.py"
    script.write_text("# bridge\n", encoding="utf-8")
    return LucidaDetailProvider(fake_python(tmp_path), script_path=script, runner=runner)


def result(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_successful_resolution_uses_managed_python_without_shell(tmp_path: Path) -> None:
    payload = {
        "type": "album",
        "title": "Album",
        "artist": "Artist",
        "cover": "",
        "tracks": [
            {
                "title": "Track",
                "artist": "Artist",
                "url": "https://music.amazon.com/tracks/B001",
            }
        ],
    }
    runner = Runner(result(json.dumps(payload)))
    adapter = provider(tmp_path, runner)

    detail = adapter.resolve("https://music.amazon.in/albums/B001")

    assert detail.kind is CatalogKind.ALBUM
    assert detail.tracks[0].title == "Track"
    command, kwargs = runner.calls[0]
    assert command[0] == str(adapter._python)
    assert command[-1] == "https://music.amazon.in/albums/B001"
    assert "shell" not in kwargs
    assert kwargs["capture_output"] is True


def test_missing_managed_environment_is_unavailable(tmp_path: Path) -> None:
    adapter = LucidaDetailProvider(tmp_path / "missing-python", script_path=tmp_path / "x.py")

    with pytest.raises(CatalogUnavailableError, match="deps install"):
        adapter.resolve("https://music.amazon.in/albums/B001")


def test_missing_bridge_script_is_unavailable(tmp_path: Path) -> None:
    adapter = LucidaDetailProvider(
        fake_python(tmp_path),
        script_path=tmp_path / "missing.py",
        runner=Runner(result("")),
    )

    with pytest.raises(CatalogUnavailableError, match="resolver is missing"):
        adapter.resolve("https://music.amazon.in/albums/B001")


def test_bridge_error_message_is_forwarded_safely(tmp_path: Path) -> None:
    runner = Runner(result("", returncode=2, stderr='{"error": "Cloudflare clearance is missing"}'))
    adapter = provider(tmp_path, runner)

    with pytest.raises(CatalogUnavailableError, match="Cloudflare clearance"):
        adapter.resolve("https://music.amazon.in/albums/B001")


def test_non_json_bridge_error_uses_generic_message(tmp_path: Path) -> None:
    runner = Runner(result("", returncode=2, stderr="traceback with secret token=abc"))
    adapter = provider(tmp_path, runner)

    with pytest.raises(CatalogUnavailableError, match="resolver failed") as caught:
        adapter.resolve("https://music.amazon.in/albums/B001")
    assert "token=abc" not in str(caught.value)


def test_timeout_is_reported(tmp_path: Path) -> None:
    runner = Runner(subprocess.TimeoutExpired([], 1))
    adapter = provider(tmp_path, runner)

    with pytest.raises(CatalogTimeoutError):
        adapter.resolve("https://music.amazon.in/albums/B001")


def test_invalid_or_oversized_output_is_reported(tmp_path: Path) -> None:
    adapter = provider(tmp_path, Runner(result("not-json")))
    with pytest.raises(CatalogResponseError, match="invalid data"):
        adapter.resolve("https://music.amazon.in/albums/B001")

    adapter = provider(tmp_path, Runner(result("x" * 2_000_001)))
    with pytest.raises(CatalogResponseError, match="too much data"):
        adapter.resolve("https://music.amazon.in/albums/B001")


def test_non_executable_python_is_unavailable(tmp_path: Path) -> None:
    python = fake_python(tmp_path)
    python.chmod(0o644)
    adapter = LucidaDetailProvider(python, script_path=tmp_path / "bridge.py")

    with pytest.raises(CatalogUnavailableError):
        adapter.resolve("https://music.amazon.in/albums/B001")
