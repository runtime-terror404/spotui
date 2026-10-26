from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from spotui.lifecycle import (
    AlreadyRunningError,
    ProcessLock,
    ProcessLockError,
    inspect_lock,
)


def test_second_instance_is_rejected_with_metadata(tmp_path: Path) -> None:
    lock_path = tmp_path / "server.lock"
    lock = ProcessLock(lock_path)
    lock.acquire({"version": "test", "urls": ["http://127.0.0.1:8765"]})

    info = inspect_lock(lock_path)
    assert info.locked is True
    assert info.metadata is not None
    assert info.metadata["pid"] == os.getpid()
    assert info.metadata["urls"] == ["http://127.0.0.1:8765"]

    with pytest.raises(AlreadyRunningError) as caught:
        ProcessLock(lock_path).acquire()

    assert caught.value.existing is not None
    assert caught.value.existing["version"] == "test"

    lock.release()
    assert lock.held is False
    assert inspect_lock(lock_path).locked is False


def test_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "server.lock"
    first = ProcessLock(lock_path)
    first.acquire()
    first.release()

    with ProcessLock(lock_path) as second:
        assert second.held is True


def test_metadata_updates_are_merged(tmp_path: Path) -> None:
    lock_path = tmp_path / "server.lock"
    lock = ProcessLock(lock_path)
    lock.acquire({"version": "0.1.0"})
    lock.update_metadata({"urls": ["http://127.0.0.1:9000"]})

    metadata = inspect_lock(lock_path).metadata
    assert metadata is not None
    assert metadata["version"] == "0.1.0"
    assert metadata["urls"] == ["http://127.0.0.1:9000"]

    lock.release()


def test_lock_file_is_private_and_parent_created(tmp_path: Path) -> None:
    lock_path = tmp_path / "nested" / "server.lock"
    lock = ProcessLock(lock_path)
    lock.acquire()

    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    lock.release()


def test_existing_lock_file_permissions_are_tightened(tmp_path: Path) -> None:
    lock_path = tmp_path / "server.lock"
    lock_path.write_text("stale", encoding="utf-8")
    lock_path.chmod(0o644)
    lock = ProcessLock(lock_path)
    lock.acquire()

    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    lock.release()


def test_inspect_missing_lock_does_not_create_it(tmp_path: Path) -> None:
    lock_path = tmp_path / "missing.lock"

    info = inspect_lock(lock_path)

    assert info.locked is False
    assert info.metadata is None
    assert not lock_path.exists()


def test_release_is_idempotent_and_use_after_acquire_is_rejected(tmp_path: Path) -> None:
    lock = ProcessLock(tmp_path / "server.lock")
    lock.release()
    lock.acquire()

    with pytest.raises(ProcessLockError, match="already acquired"):
        lock.acquire()

    lock.release()
    lock.release()


def test_os_releases_lock_when_process_dies(tmp_path: Path) -> None:
    lock_path = tmp_path / "server.lock"
    script = (
        "import sys, time\n"
        "from spotui.lifecycle import ProcessLock\n"
        "lock = ProcessLock(sys.argv[1])\n"
        "lock.acquire({'child': True})\n"
        "print('ready', flush=True)\n"
        "time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(AlreadyRunningError):
            ProcessLock(lock_path).acquire()

        process.terminate()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    # The OS has released the dead process's lock; stale metadata is ignored.
    lock = ProcessLock(lock_path)
    lock.acquire({"after": "crash"})
    metadata = inspect_lock(lock_path).metadata
    assert metadata is not None
    assert metadata["after"] == "crash"
    lock.release()
