from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spotui.app import create_app
from spotui.schemas.errors import ErrorCode
from tests.api.helpers import assert_problem


@pytest.fixture
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('ok');", encoding="utf-8")
    return dist


def test_built_frontend_is_served_without_breaking_api(runtime, web_dist: Path) -> None:
    app = create_app(runtime, web_dist=web_dist)

    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert 'id="root"' in root.text

        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        assert asset.text == "console.log('ok');"

        assert client.get("/api/v1/health").status_code == 200
        assert_problem(
            client.get("/api/v1/does-not-exist"),
            404,
            ErrorCode.NOT_FOUND,
        )
        assert client.get("/docs").status_code == 200


def test_incomplete_explicit_frontend_build_fails(runtime, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="incomplete"):
        create_app(runtime, web_dist=tmp_path / "missing")
