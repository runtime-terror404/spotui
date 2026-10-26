from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from spotui.api.v1.dependencies import ServicesDependency
from spotui.schemas.catalog import SearchResponse, search_response

router = APIRouter()


@router.get(
    "/search",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="Search Amazon Music",
)
def search_amazon(
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=200,
            description="Artist, album, playlist, or track query",
        ),
    ],
    services: ServicesDependency,
) -> SearchResponse:
    normalized_query = " ".join(q.split())
    sections = services.search.search(q)
    return search_response(normalized_query, sections)
