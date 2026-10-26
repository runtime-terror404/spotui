from __future__ import annotations

from fastapi import APIRouter

from spotui.api.v1.dependencies import SystemInfoDependency
from spotui.schemas.system import SystemInfoResponse, system_info_response

router = APIRouter()


@router.get(
    "/system/info",
    response_model=SystemInfoResponse,
    summary="Read application paths and downloader information",
)
def read_system_info(service: SystemInfoDependency) -> SystemInfoResponse:
    return system_info_response(service.info())
