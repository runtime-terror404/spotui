from __future__ import annotations

import subprocess

from spotui import __version__
from spotui.app import create_app
from spotui.services.system_info import SystemInfoService
from tests.api.helpers import CSRFTestClient as TestClient


def test_system_info_reports_application_and_downloader_paths(
    env, runtime, services
) -> None:
    executable = env.paths.lucidadl_executable
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)

    def runner(command, **_kwargs):  # noqa: ANN001, ANN202
        return subprocess.CompletedProcess(
            command,
            0,
            "Music       : /mnt/Shared/Music\n",
            "",
        )

    services.system_info = SystemInfoService(env.paths, runner=runner)
    runtime.services = services
    app = create_app(runtime, serve_frontend=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    assert response.json() == {
        "version": __version__,
        "root": str(env.paths.data_dir),
        "config_file": str(env.paths.config_file),
        "download_directory": "/mnt/Shared/Music",
        "downloader_available": True,
    }
