"""Amazon Music entity-detail use case."""

from __future__ import annotations

from spotui.domain.amazon import AmazonUrlError, parse_amazon_url
from spotui.domain.catalog import DETAIL_KINDS, EntityDetail
from spotui.providers.amazon.base import AmazonCatalog


class EntityDetailsService:
    def __init__(self, provider: AmazonCatalog) -> None:
        self._provider = provider

    def detail(self, url: str) -> EntityDetail:
        target = parse_amazon_url(url)
        if target.kind not in DETAIL_KINDS:
            raise AmazonUrlError("This Amazon Music URL does not have a detail view.")
        return self._provider.detail(target)
