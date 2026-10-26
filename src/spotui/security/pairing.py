"""Cryptographic pairing-code generation and bounded attempt limiting."""

from __future__ import annotations

import math
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


def generate_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class PairingAttemptLimiter:
    """Conservative per-source and global failure windows.

    Five failures from one source within fifteen minutes lock that source for
    fifteen minutes. Thirty failures across all sources within the same window
    lock pairing globally for fifteen minutes. Successful pairing resets only
    that source's failures.
    """

    def __init__(
        self,
        *,
        source_limit: int = 5,
        global_limit: int = 30,
        window_seconds: float = 15 * 60,
        lockout_seconds: float = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source_limit = source_limit
        self._global_limit = global_limit
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._clock = clock
        self._source_failures: dict[str, deque[float]] = defaultdict(deque)
        self._source_locked_until: dict[str, float] = {}
        self._global_failures: deque[float] = deque()
        self._global_locked_until = 0.0
        self._lock = threading.Lock()

    def retry_after(self, source_ip: str) -> int:
        now = self._clock()
        with self._lock:
            self._prune(now)
            locked_until = max(
                self._global_locked_until,
                self._source_locked_until.get(source_ip, 0.0),
            )
            if locked_until <= now:
                return 0
            return max(1, math.ceil(locked_until - now))

    def record_failure(self, source_ip: str) -> int:
        now = self._clock()
        with self._lock:
            self._prune(now)
            failures = self._source_failures[source_ip]
            failures.append(now)
            if len(failures) >= self._source_limit:
                self._source_locked_until[source_ip] = now + self._lockout_seconds
            self._global_failures.append(now)
            if len(self._global_failures) >= self._global_limit:
                self._global_locked_until = now + self._lockout_seconds
            locked_until = max(
                self._global_locked_until,
                self._source_locked_until.get(source_ip, 0.0),
            )
            return max(1, math.ceil(locked_until - now))

    def record_success(self, source_ip: str) -> None:
        with self._lock:
            self._source_failures.pop(source_ip, None)
            self._source_locked_until.pop(source_ip, None)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        for source_ip, failures in list(self._source_failures.items()):
            while failures and failures[0] <= cutoff:
                failures.popleft()
            if not failures and self._source_locked_until.get(source_ip, 0) <= now:
                self._source_failures.pop(source_ip, None)
                self._source_locked_until.pop(source_ip, None)
        while self._global_failures and self._global_failures[0] <= cutoff:
            self._global_failures.popleft()
        for source_ip, locked_until in list(self._source_locked_until.items()):
            if locked_until <= now:
                self._source_locked_until.pop(source_ip, None)
