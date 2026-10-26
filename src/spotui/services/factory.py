"""Build production application services."""

from __future__ import annotations

from spotui.paths import Paths
from spotui.providers.amazon.browser import AmazonBrowserProvider
from spotui.providers.amazon.facade import AmazonCatalogProvider
from spotui.providers.amazon.lucida import LucidaDetailProvider
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.search import SearchService


def build_application_services(paths: Paths) -> ApplicationServices:
    browser = AmazonBrowserProvider()
    lucida = LucidaDetailProvider(paths.lucidadl_python)
    catalog = AmazonCatalogProvider(browser=browser, lucida=lucida)
    return ApplicationServices(
        search=SearchService(catalog),
        entity_details=EntityDetailsService(catalog),
        resources=(catalog,),
    )
