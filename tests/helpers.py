from __future__ import annotations

from pathlib import Path

from spotui.paths import Paths


def write_config(paths: Paths, contents: str) -> None:
    path: Path = paths.config_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
