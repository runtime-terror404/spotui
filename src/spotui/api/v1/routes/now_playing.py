from __future__ import annotations

from fastapi import APIRouter

from spotui.api.v1.dependencies import NowPlayingDependency
from spotui.schemas.now_playing import NowPlayingResponse, now_playing_response

router = APIRouter()


@router.get(
    "/now-playing",
    response_model=NowPlayingResponse,
    response_model_exclude_none=True,
    summary="Read the current MPRIS track",
)
def read_now_playing(service: NowPlayingDependency) -> NowPlayingResponse:
    return now_playing_response(service.status())
