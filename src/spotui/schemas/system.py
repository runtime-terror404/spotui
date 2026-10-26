from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from spotui.services.system_info import SystemInfo


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True] = True
    version: str
    uptime_seconds: float = Field(ge=0)


class SystemInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    root: str
    config_file: str
    download_directory: str | None = None
    downloader_available: bool


def system_info_response(info: SystemInfo) -> SystemInfoResponse:
    return SystemInfoResponse(
        version=info.version,
        root=info.root,
        config_file=info.config_file,
        download_directory=info.download_directory,
        downloader_available=info.downloader_available,
    )
