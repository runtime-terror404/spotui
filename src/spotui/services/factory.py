"""Build production application services."""

from __future__ import annotations

from spotui.config import AppConfig
from spotui.paths import Paths
from spotui.persistence.database import Database
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.providers.amazon.browser import AmazonBrowserProvider
from spotui.providers.amazon.facade import AmazonCatalogProvider
from spotui.providers.amazon.lucida import LucidaDetailProvider
from spotui.providers.downloader.lucidadl import LucidadlDownloader
from spotui.providers.library.legacy import (
    LegacyLibraryIndex,
    default_lucidadl_state_file,
)
from spotui.providers.mpris.playerctl import PlayerctlMprisProvider
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.now_playing import NowPlayingService
from spotui.services.queue import QueueService
from spotui.services.search import SearchService
from spotui.workers.download_worker import DownloadWorker


def build_application_services(
    config: AppConfig,
    paths: Paths,
    database: Database,
) -> ApplicationServices:
    library = LegacyLibraryIndex(default_lucidadl_state_file())
    browser = AmazonBrowserProvider()
    lucida = LucidaDetailProvider(paths.lucidadl_python)
    catalog = AmazonCatalogProvider(browser=browser, lucida=lucida)

    downloader = LucidadlDownloader(paths.lucidadl_executable)
    repository = DownloadJobRepository(database.session_factory)
    worker = DownloadWorker(
        repository,
        downloader,
        cancel_grace_seconds=config.queue.cancel_grace_seconds,
        shutdown_grace_seconds=config.queue.shutdown_grace_seconds,
        job_timeout_seconds=config.queue.job_timeout_seconds,
    )
    queue = QueueService(
        repository,
        worker,
        downloader,
        library=library,
    )
    return ApplicationServices(
        search=SearchService(catalog, library=library),
        entity_details=EntityDetailsService(catalog, library=library),
        queue=queue,
        now_playing=NowPlayingService(PlayerctlMprisProvider()),
        resources=(catalog,),
    )
