"""Build production application services."""

from __future__ import annotations

from spotui.config import AppConfig
from spotui.paths import Paths
from spotui.persistence.database import Database
from spotui.persistence.repositories.download_jobs import DownloadJobRepository
from spotui.persistence.repositories.library import LibraryRepository
from spotui.providers.amazon.browser import AmazonBrowserProvider
from spotui.providers.amazon.facade import AmazonCatalogProvider
from spotui.providers.amazon.lucida import LucidaDetailProvider
from spotui.providers.audio_tags.mutagen import MutagenTagReader
from spotui.providers.downloader.lucidadl import LucidadlDownloader
from spotui.providers.mpris.playerctl import PlayerctlMprisProvider
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.library import LibraryService
from spotui.services.now_playing import NowPlayingService
from spotui.services.queue import QueueService
from spotui.services.search import SearchService
from spotui.workers.download_worker import DownloadWorker
from spotui.workers.library_scanner import LibraryScanWorker


def build_application_services(
    config: AppConfig,
    paths: Paths,
    database: Database,
) -> ApplicationServices:
    browser = AmazonBrowserProvider()
    lucida = LucidaDetailProvider(paths.lucidadl_python)
    catalog = AmazonCatalogProvider(browser=browser, lucida=lucida)

    library_repository = LibraryRepository(database.session_factory)
    library = LibraryService(
        library_repository,
        LibraryScanWorker(
            library_repository,
            MutagenTagReader(),
            config.library.roots,
            refresh_seconds=config.library.refresh_seconds,
            scan_on_startup=config.library.scan_on_startup,
        ),
    )

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
        library=library,
        resources=(catalog,),
    )
