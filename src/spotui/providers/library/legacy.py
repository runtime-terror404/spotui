"""Compatibility library index over lucidadl's state.json.

This preserves the existing in-library badges and batch skip behavior until the
durable library index from the library phase replaces it. Existing media files
are only read for existence/path matching; they are never modified.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

_ASIN_RE = re.compile(r"(?:trackAsin=|/tracks/)([A-Za-z0-9]{10})")


def default_lucidadl_state_file(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    home_override = env.get("LUCIDADL_HOME", "").strip()
    if home_override:
        return Path(home_override).expanduser() / "state.json"
    data_home = env.get("XDG_DATA_HOME", "").strip()
    base = (
        Path(data_home).expanduser()
        if data_home and Path(data_home).is_absolute()
        else Path.home() / ".local" / "share"
    )
    return base / "lucidadl" / "state.json"


def _asin_from_url(url: str) -> str | None:
    match = _ASIN_RE.search(url or "")
    return match.group(1).upper() if match else None


def _norm_title(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _norm_tokens(value: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


class LegacyLibraryIndex:
    """Refreshable in-memory index of completed lucidadl downloads."""

    def __init__(
        self,
        state_file: Path | None = None,
        *,
        refresh_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state_file = state_file or default_lucidadl_state_file()
        self._refresh_seconds = refresh_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._last_refresh: float | None = None
        self._asins: set[str] = set()
        self._titles: dict[str, set[str]] = {}

    @property
    def state_file(self) -> Path:
        return self._state_file

    def contains(
        self,
        track_url: str,
        title: str | None = None,
        artist: str | None = None,
    ) -> bool:
        asin = _asin_from_url(track_url)
        with self._lock:
            self._refresh_if_needed()
            if asin and asin in self._asins:
                return True
            if not title:
                return False
            stored = self._titles.get(_norm_title(title))
            if not stored:
                return False
            if not artist:
                return True
            return bool(stored & _norm_tokens(artist))

    def refresh(self) -> None:
        with self._lock:
            self._load()
            self._last_refresh = self._clock()

    def _refresh_if_needed(self) -> None:
        if (
            self._last_refresh is not None
            and self._clock() - self._last_refresh < self._refresh_seconds
        ):
            return
        self._load()
        self._last_refresh = self._clock()

    def _load(self) -> None:
        asins: set[str] = set()
        titles: dict[str, set[str]] = {}
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("invalid state shape")
            done = data.get("done") or {}
            if not isinstance(done, dict):
                raise ValueError("invalid state shape")
            for key, paths in done.items():
                if not isinstance(key, str) or not isinstance(paths, list):
                    continue
                existing = [path for path in paths if isinstance(path, str) and Path(path).exists()]
                if not existing:
                    continue
                asin = _asin_from_url(key)
                if asin:
                    asins.add(asin)
                for path in existing:
                    parts = Path(path).parts
                    if "Artists" not in parts:
                        continue
                    artist_index = parts.index("Artists")
                    if artist_index + 2 >= len(parts):
                        continue
                    artist_name = parts[artist_index + 1]
                    normalized_title = _norm_title(Path(parts[-1]).stem)
                    if not normalized_title:
                        continue
                    titles.setdefault(normalized_title, set()).update(
                        _norm_tokens(artist_name)
                    )
        except (OSError, ValueError):
            asins, titles = set(), {}
        self._asins = asins
        self._titles = titles
