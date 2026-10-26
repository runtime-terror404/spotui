"""Process lifecycle primitives.

The single-instance guard uses an OS advisory lock (``flock``). The kernel
releases it when the owning process exits, including after a crash, so there is
no unsafe PID-file staleness logic. The file holds diagnostic metadata only;
the lock is the source of truth.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

_MAX_METADATA_BYTES = 64 * 1024


class ProcessLockError(RuntimeError):
    """Base class for single-instance lock failures."""


class AlreadyRunningError(ProcessLockError):
    """Another live process holds the lock for this data directory."""

    def __init__(self, lock_path: Path, existing: dict[str, Any] | None) -> None:
        self.lock_path = lock_path
        self.existing = existing
        super().__init__(f"another SpotUI server is already running (lock: {lock_path})")


class LockPathError(ProcessLockError):
    """The lock file could not be created or locked."""


def _read_metadata_fd(fd: int) -> dict[str, Any] | None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, _MAX_METADATA_BYTES)
        if not raw.strip():
            return None
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


@dataclass(slots=True)
class LockInfo:
    """Diagnostic snapshot; never used to decide whether the lock is held."""

    locked: bool
    metadata: dict[str, Any] | None = None


def inspect_lock(path: Path) -> LockInfo:
    """Probe *path* without taking ownership of the lock."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    except FileNotFoundError:
        return LockInfo(locked=False)
    except OSError:
        return LockInfo(locked=False)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return LockInfo(locked=True, metadata=_read_metadata_fd(fd))
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return LockInfo(locked=False, metadata=_read_metadata_fd(fd))
    finally:
        os.close(fd)


@dataclass(slots=True)
class ProcessLock:
    """An exclusive OS lock held for the lifetime of the server process."""

    path: Path
    _fd: int | None = field(default=None, init=False, repr=False)
    _metadata: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self, metadata: Mapping[str, Any] | None = None) -> None:
        if self._fd is not None:
            raise ProcessLockError("this lock instance is already acquired")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        except OSError as exc:
            raise LockPathError(f"cannot open lock file {self.path}: {exc}") from exc

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            existing = _read_metadata_fd(fd)
            os.close(fd)
            raise AlreadyRunningError(self.path, existing) from exc
        except OSError as exc:
            os.close(fd)
            raise LockPathError(f"cannot lock {self.path}: {exc}") from exc

        self._fd = fd
        self._metadata = dict(metadata or {})
        try:
            os.fchmod(fd, 0o600)
            self.update_metadata()
        except Exception:
            self.release()
            raise

    def update_metadata(self, metadata: Mapping[str, Any] | None = None) -> None:
        """Publish diagnostic metadata. The OS lock remains authoritative."""
        if self._fd is None:
            raise ProcessLockError("the process lock is not held")
        if metadata:
            self._metadata.update(metadata)
        payload = {
            **self._metadata,
            "pid": os.getpid(),
            "locked_at": int(time.time()),
        }
        data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        if len(data) > _MAX_METADATA_BYTES:
            raise ProcessLockError("lock metadata is too large")
        try:
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.ftruncate(self._fd, 0)
            remaining = memoryview(data)
            while remaining:
                written = os.write(self._fd, remaining)
                if written <= 0:
                    raise OSError("short write while publishing lock metadata")
                remaining = remaining[written:]
            os.fsync(self._fd)
        except OSError as exc:
            raise LockPathError(f"cannot write metadata to {self.path}: {exc}") from exc

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> ProcessLock:
        if not self.held:
            self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
