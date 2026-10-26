"""Playwright-backed Amazon Music search and detail adapter.

Playwright's synchronous API must stay on the thread that created it, so one
worker thread owns one Chromium page and serializes browser work through a
queue. The worker is lazy: Chromium starts on the first request and is closed
during application shutdown.
"""

from __future__ import annotations

import logging
import queue
import threading
import urllib.parse
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from spotui.domain.catalog import EntityDetail, SearchSection
from spotui.domain.errors import (
    CatalogError,
    CatalogResponseError,
    CatalogTimeoutError,
    CatalogUnavailableError,
)
from spotui.providers.amazon.parsing import (
    parse_artist_payload,
    parse_community_playlist_rows,
    parse_search_payload,
)

logger = logging.getLogger("spotui.amazon.browser")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)
SEARCH_URL = "https://music.amazon.in/search/"
SEARCH_TIMEOUT = 90.0
ARTIST_TIMEOUT = 120.0
PLAYLIST_TIMEOUT = 180.0

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _BrowserJob:
    operation: str
    callback: Callable[[], Any]
    future: Future[Any]


class AmazonBrowserWorker:
    """Serialize Playwright work on one dedicated thread."""

    def __init__(self) -> None:
        self._jobs: queue.Queue[_BrowserJob | None] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._playwright = None
        self._browser = None
        self._page = None

    def submit(self, operation: str, callback: Callable[[], T], timeout: float) -> T:
        with self._lock:
            if self._closed:
                raise CatalogUnavailableError("The Amazon Music browser is shutting down.")
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run,
                    name="amazon-browser",
                    daemon=True,
                )
                self._thread.start()

        future: Future[Any] = Future()
        self._jobs.put(_BrowserJob(operation, callback, future))
        try:
            return cast(T, future.result(timeout=timeout))
        except FutureTimeoutError as exc:
            raise CatalogTimeoutError(
                f"Amazon Music {operation} did not respond in time."
            ) from exc

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            thread = self._thread
        if thread is None:
            return
        self._jobs.put(None)
        thread.join(timeout=15)
        if thread.is_alive():
            logger.warning("Amazon browser thread did not stop within the grace period")
        with self._lock:
            self._thread = None

    def _run(self) -> None:
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    break
                try:
                    result = self._execute(job.operation, job.callback)
                except BaseException as exc:  # surfaced to the request thread
                    job.future.set_exception(exc)
                else:
                    job.future.set_result(result)
        finally:
            self._close_browser()

    @staticmethod
    def _execute(operation: str, callback: Callable[[], T]) -> T:
        try:
            return callback()
        except CatalogError:
            raise
        except Exception as exc:
            logger.exception("Amazon Music %s failed", operation)
            raise CatalogResponseError(f"Amazon Music {operation} failed.") from exc

    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page(user_agent=USER_AGENT)
        except Exception as exc:
            self._close_browser()
            logger.exception("Amazon Music browser failed to start")
            raise CatalogUnavailableError(
                "The Amazon Music browser runtime is unavailable. "
                "Run 'spotui deps check' and install its browser."
            ) from exc

    def _capture(self, url: str, api_key: str) -> tuple[Any | None, str]:
        self._ensure_browser()
        if self._page is None:
            raise CatalogUnavailableError("The Amazon Music browser page is unavailable.")
        captured: list[Any] = []

        def on_response(response) -> None:  # noqa: ANN001 - Playwright response
            if api_key in response.url and response.request.resource_type in ("fetch", "xhr"):
                try:
                    captured.append(response.json())
                except Exception:
                    pass

        self._page.on("response", on_response)
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            for _ in range(28):
                if captured:
                    break
                self._page.wait_for_timeout(500)
            self._page.wait_for_timeout(400)
            title = self._page.title()
        except CatalogError:
            raise
        except Exception as exc:
            raise CatalogResponseError("Amazon Music page could not be loaded.") from exc
        finally:
            self._page.remove_listener("response", on_response)
        return (captured[0] if captured else None), title

    def search(self, query: str) -> tuple[SearchSection, ...]:
        data, _ = self.submit(
            "search",
            lambda: self._capture(
                SEARCH_URL + urllib.parse.quote(query),
                "showSearch",
            ),
            timeout=SEARCH_TIMEOUT,
        )
        if data is None:
            raise CatalogResponseError("Amazon Music did not return search results.")
        return parse_search_payload(data)

    def artist_detail(self, url: str) -> EntityDetail:
        data, page_title = self.submit(
            "artist detail",
            lambda: self._capture(url, "showCatalogArtist"),
            timeout=ARTIST_TIMEOUT,
        )
        if data is None:
            raise CatalogResponseError("Amazon Music did not return artist details.")
        return parse_artist_payload(data, page_title)

    def community_playlist_detail(self, url: str) -> EntityDetail:
        rows, page_title = self.submit(
            "community playlist detail",
            lambda: self._read_community_playlist(url),
            timeout=PLAYLIST_TIMEOUT,
        )
        return parse_community_playlist_rows(rows, page_title)

    def _read_community_playlist(self, url: str) -> tuple[list[dict[str, Any]], str]:
        self._ensure_browser()
        if self._page is None:
            raise CatalogUnavailableError("The Amazon Music browser page is unavailable.")
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            self._page.wait_for_selector(
                "music-image-row[primary-text]", timeout=45_000
            )

            def read_rows() -> list[dict[str, Any]]:
                return self._page.eval_on_selector_all(
                    "music-image-row[primary-text]",
                    """els => els.map(e => ({
                        key: e.getAttribute('data-key') || '',
                        title: e.getAttribute('primary-text') || '',
                        artist: e.getAttribute('secondary-text-1') || '',
                        href: e.getAttribute('primary-href') || '',
                        style: e.getAttribute('style') || ''
                    }))""",
                )

            collected: list[dict[str, Any]] = []
            seen: set[tuple[str, str, str]] = set()

            def ingest() -> None:
                for row in read_rows():
                    identity = (
                        str(row.get("key", "")),
                        str(row.get("title", "")),
                        str(row.get("href", "")),
                    )
                    if identity not in seen:
                        seen.add(identity)
                        collected.append(row)

            ingest()
            previous = -1
            stalls = 0
            while len(seen) != previous and stalls < 2:
                previous = len(seen)
                for _ in range(4):
                    self._page.mouse.wheel(0, 8000)
                    self._page.wait_for_timeout(800)
                ingest()
                stalls = stalls + 1 if len(seen) == previous else 0
            return collected, self._page.title()
        except CatalogError:
            raise
        except Exception as exc:
            raise CatalogResponseError(
                "The Amazon Music community playlist could not be read."
            ) from exc

    def _close_browser(self) -> None:
        page, browser, playwright = self._page, self._browser, self._playwright
        self._page = self._browser = self._playwright = None
        if page is not None:
            try:
                page.close()
            except Exception:
                logger.debug("Amazon page cleanup failed", exc_info=True)
        if browser is not None:
            try:
                browser.close()
            except Exception:
                logger.debug("Amazon browser cleanup failed", exc_info=True)
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                logger.debug("Playwright cleanup failed", exc_info=True)


class AmazonBrowserProvider:
    """Catalog-facing wrapper around the browser worker."""

    def __init__(self) -> None:
        self._worker = AmazonBrowserWorker()

    def search(self, query: str) -> tuple[SearchSection, ...]:
        return self._worker.search(query)

    def artist_detail(self, url: str) -> EntityDetail:
        return self._worker.artist_detail(url)

    def community_playlist_detail(self, url: str) -> EntityDetail:
        return self._worker.community_playlist_detail(url)

    def close(self) -> None:
        self._worker.close()
