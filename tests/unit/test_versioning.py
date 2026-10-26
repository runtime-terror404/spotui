from __future__ import annotations

import json
import tomllib
from pathlib import Path

from spotui import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_package_version_is_single_sourced_from_dunder_init() -> None:
    metadata = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" not in metadata["project"]
    assert metadata["project"]["dynamic"] == ["version"]
    assert metadata["tool"]["hatch"]["version"]["path"] == "src/spotui/__init__.py"


def test_lock_and_frontend_versions_match_the_package() -> None:
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    spotui_entries = [item for item in lock["package"] if item["name"] == "spotui"]
    assert len(spotui_entries) == 1
    # Dynamic project versions are resolved at build time; a static value in
    # the lockfile would create a second source of truth.
    assert "version" not in spotui_entries[0]

    frontend = json.loads(
        (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    frontend_lock = json.loads(
        (REPO_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    assert frontend["version"] == __version__
    assert frontend_lock["version"] == __version__
    assert frontend_lock["packages"][""]["version"] == __version__
