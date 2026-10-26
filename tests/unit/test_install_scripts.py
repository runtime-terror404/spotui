from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL = REPO_ROOT / "scripts" / "install.sh"
UNINSTALL = REPO_ROOT / "scripts" / "uninstall.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="shell installer tests require bash",
)

FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$UV_LOG"
if [[ "${1:-}" == "venv" ]]; then
    target="${@: -1}"
    mkdir -p "$target/bin"
    cat > "$target/bin/spotui" <<'FAKE_SPOTUI'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$FAKE_SPOTUI_LOG"
if [[ "${1:-}" == "--version" ]]; then
    printf 'spotui 0.1.0\\n'
    exit 0
fi
if [[ "${1:-}" == "status" ]]; then
    printf '%s\\n' "${FAKE_SERVER_STATUS:-Server: not running}"
    exit 0
fi
exit 0
FAKE_SPOTUI
    chmod +x "$target/bin/spotui"
fi
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
set -euo pipefail
out=""
url=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
        out="$2"
        shift 2
        continue
    fi
    if [[ "$1" == http* ]]; then
        url="$1"
    fi
    shift
done
printf '%s\\n' "$url" >> "$CURL_LOG"
name="${url##*/}"
if [[ "$name" == "SHA256SUMS" ]]; then
    cp "$FAKE_CURL_FIXTURES/SHA256SUMS" "$out"
elif [[ -f "$FAKE_CURL_FIXTURES/$name" ]]; then
    cp "$FAKE_CURL_FIXTURES/$name" "$out"
else
    exit 22
fi
"""


@pytest.fixture
def shell_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    stub_dir = tmp_path / "stub"
    tmp_dir = tmp_path / "tmp"
    for directory in (home, bin_dir, stub_dir, tmp_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (stub_dir / "uv").write_text(FAKE_UV, encoding="utf-8")
    (stub_dir / "uv").chmod(0o755)
    (stub_dir / "curl").write_text(FAKE_CURL, encoding="utf-8")
    (stub_dir / "curl").chmod(0o755)

    environment = {
        "HOME": str(home),
        "PATH": f"{stub_dir}:{bin_dir}:/usr/bin:/bin",
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_BIN_HOME": str(bin_dir),
        "TMPDIR": str(tmp_dir),
        "UV_LOG": str(tmp_path / "uv.log"),
        "FAKE_SPOTUI_LOG": str(tmp_path / "spotui.log"),
    }
    return environment


def wheel(tmp_path: Path) -> Path:
    path = tmp_path / "spotui-0.1.0-py3-none-any.whl"
    path.write_bytes(b"not-a-real-wheel-but-the-stub-does-not-care")
    return path


def run_script(
    script: Path,
    arguments: list[str],
    *,
    environment: dict[str, str],
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(environment)
    return subprocess.run(
        [str(script), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        env=merged,
        input=input_text,
    )


def test_install_is_idempotent_and_registers_launcher(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    arguments = ["--wheel", str(wheel(tmp_path))]

    first = run_script(INSTALL, arguments, environment=shell_env)
    second = run_script(INSTALL, arguments, environment=shell_env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    data_dir = Path(shell_env["XDG_DATA_HOME"]) / "spotui"
    env_dir = data_dir / "envs" / "spotui"
    launcher = Path(shell_env["XDG_BIN_HOME"]) / "spotui"
    assert (env_dir / "bin" / "spotui").is_file()
    assert launcher.is_symlink()
    assert os.readlink(launcher) == str(env_dir / "bin" / "spotui")
    assert not list(launcher.parent.glob("spotui.legacy-*"))
    uv_log = Path(shell_env["UV_LOG"]).read_text(encoding="utf-8")
    assert "venv --allow-existing --python 3.11" in uv_log
    assert "pip install --python" in uv_log
    calls = Path(shell_env["FAKE_SPOTUI_LOG"]).read_text(encoding="utf-8")
    assert "--version" in calls
    assert "db upgrade" in calls


def test_install_verifies_a_release_download(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    fixtures = tmp_path / "release"
    fixtures.mkdir()
    wheel_bytes = b"release-wheel-bytes"
    wheel_name = "spotui-0.1.0-py3-none-any.whl"
    (fixtures / wheel_name).write_bytes(wheel_bytes)
    digest = hashlib.sha256(wheel_bytes).hexdigest()
    (fixtures / "SHA256SUMS").write_text(
        f"{digest}  {wheel_name}\n",
        encoding="utf-8",
    )
    shell_env["FAKE_CURL_FIXTURES"] = str(fixtures)
    shell_env["CURL_LOG"] = str(tmp_path / "curl.log")

    result = run_script(
        INSTALL,
        ["--version", "0.1.0"],
        environment=shell_env,
    )

    assert result.returncode == 0, result.stderr
    urls = Path(shell_env["CURL_LOG"]).read_text(encoding="utf-8")
    assert f"/releases/download/v0.1.0/{wheel_name}" in urls
    assert "SHA256SUMS" in urls


def test_install_rejects_a_mismatched_release_checksum(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    fixtures = tmp_path / "release"
    fixtures.mkdir()
    wheel_name = "spotui-0.1.0-py3-none-any.whl"
    (fixtures / wheel_name).write_bytes(b"tampered")
    (fixtures / "SHA256SUMS").write_text(
        f"{'0' * 64}  {wheel_name}\n",
        encoding="utf-8",
    )
    shell_env["FAKE_CURL_FIXTURES"] = str(fixtures)
    shell_env["CURL_LOG"] = str(tmp_path / "curl.log")

    result = run_script(
        INSTALL,
        ["--version", "0.1.0"],
        environment=shell_env,
    )

    assert result.returncode == 1
    assert "checksum verification failed" in result.stderr


def test_install_preserves_an_existing_launcher(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    launcher = Path(shell_env["XDG_BIN_HOME"]) / "spotui"
    launcher.write_text("#!/bin/sh\necho legacy\n", encoding="utf-8")

    result = run_script(
        INSTALL,
        ["--wheel", str(wheel(tmp_path))],
        environment=shell_env,
    )

    assert result.returncode == 0, result.stderr
    backups = list(launcher.parent.glob("spotui.legacy-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert launcher.is_symlink()


def test_install_refuses_to_upgrade_a_running_server(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    shell_env["FAKE_SERVER_STATUS"] = "Server: running (pid 123; http://127.0.0.1:8765)"

    result = run_script(
        INSTALL,
        ["--wheel", str(wheel(tmp_path))],
        environment=shell_env,
    )

    assert result.returncode == 1
    assert "stop it before installing" in result.stderr


def test_install_can_write_and_enable_the_user_service(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    result = run_script(
        INSTALL,
        ["--wheel", str(wheel(tmp_path)), "--service", "--enable-service"],
        environment=shell_env,
    )

    assert result.returncode == 0, result.stderr
    calls = Path(shell_env["FAKE_SPOTUI_LOG"]).read_text(encoding="utf-8")
    assert "service install --exec" in calls
    assert "service enable" in calls


def test_uninstall_removes_code_but_preserves_user_state(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    installed = run_script(
        INSTALL,
        ["--wheel", str(wheel(tmp_path))],
        environment=shell_env,
    )
    assert installed.returncode == 0, installed.stderr

    data_dir = Path(shell_env["XDG_DATA_HOME"]) / "spotui"
    state_dir = Path(shell_env["XDG_STATE_HOME"]) / "spotui"
    config_dir = Path(shell_env["XDG_CONFIG_HOME"]) / "spotui"
    cache_dir = Path(shell_env["XDG_CACHE_HOME"]) / "spotui"
    database = data_dir / "spotui.sqlite3"
    songs = tmp_path / "Music" / "song.flac"
    for path in (database, state_dir / "logs" / "spotui.log", config_dir / "config.toml"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserve me", encoding="utf-8")
    cache_dir.mkdir(parents=True)
    lucidadl = data_dir / "envs" / "lucidadl" / "bin" / "lucida"
    lucidadl.parent.mkdir(parents=True)
    lucidadl.write_text("downloader", encoding="utf-8")
    songs.parent.mkdir(parents=True)
    songs.write_text("music", encoding="utf-8")

    result = run_script(UNINSTALL, [], environment=shell_env)
    second = run_script(UNINSTALL, [], environment=shell_env)

    assert result.returncode == 0, result.stderr
    assert second.returncode == 0, second.stderr
    assert not (data_dir / "envs" / "spotui").exists()
    assert not (Path(shell_env["XDG_BIN_HOME"]) / "spotui").exists()
    assert database.read_text(encoding="utf-8") == "preserve me"
    assert (config_dir / "config.toml").exists()
    assert (state_dir / "logs" / "spotui.log").exists()
    assert cache_dir.exists()
    assert lucidadl.exists()
    assert songs.read_text(encoding="utf-8") == "music"


def test_purge_requires_confirmation_and_never_touches_music(
    shell_env: dict[str, str], tmp_path: Path
) -> None:
    installed = run_script(
        INSTALL,
        ["--wheel", str(wheel(tmp_path))],
        environment=shell_env,
    )
    assert installed.returncode == 0, installed.stderr

    data_dir = Path(shell_env["XDG_DATA_HOME"]) / "spotui"
    config_dir = Path(shell_env["XDG_CONFIG_HOME"]) / "spotui"
    state_dir = Path(shell_env["XDG_STATE_HOME"]) / "spotui"
    cache_dir = Path(shell_env["XDG_CACHE_HOME"]) / "spotui"
    for directory in (config_dir, state_dir, cache_dir, data_dir):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "marker").write_text("data", encoding="utf-8")
    songs = tmp_path / "Music" / "song.flac"
    songs.parent.mkdir(parents=True)
    songs.write_text("music", encoding="utf-8")

    refused = run_script(
        UNINSTALL,
        ["--purge-data"],
        environment=shell_env,
        input_text="",
    )
    assert refused.returncode == 1
    assert data_dir.exists()

    purged = run_script(
        UNINSTALL,
        ["--purge-data", "--yes"],
        environment=shell_env,
    )

    assert purged.returncode == 0, purged.stderr
    for directory in (config_dir, state_dir, cache_dir, data_dir):
        assert not directory.exists()
    assert songs.read_text(encoding="utf-8") == "music"
