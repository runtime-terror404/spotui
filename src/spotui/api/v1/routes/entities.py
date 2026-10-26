from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from spotui.api.v1.dependencies import ServicesDependency
from spotui.schemas.catalog import EntityDetailResult, entity_detail_response

router = APIRouter()


@router.get(
    "/entities/detail",
    response_model=EntityDetailResult,
    response_model_exclude_none=True,
    summary="Resolve an Amazon Music artist, album, or playlist",
)
def entity_detail(
    url: Annotated[
        str,
        Query(
            min_length=1,
            max_length=2048,
            description="Amazon Music artist, album, playlist, or community playlist URL",
        ),
    ],
    services: ServicesDependency,
) -> EntityDetailResult:
    return entity_detail_response(services.entity_details.detail(url))
