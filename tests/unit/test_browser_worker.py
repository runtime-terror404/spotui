from __future__ import annotations

import time

import pytest

from spotui.domain.errors import (
    CatalogResponseError,
    CatalogTimeoutError,
    CatalogUnavailableError,
)
from spotui.providers.amazon.browser import AmazonBrowserProvider, AmazonBrowserWorker


def test_worker_runs_callbacks_and_closes() -> None:
    worker = AmazonBrowserWorker()
    try:
        assert worker.submit("test", lambda: 42, timeout=1.0) == 42
    finally:
        worker.close()
    worker.close()


def test_worker_rejects_submit_after_close() -> None:
    worker = AmazonBrowserWorker()
    worker.close()

    with pytest.raises(CatalogUnavailableError):
        worker.submit("test", lambda: 1, timeout=1.0)


def test_worker_times_out() -> None:
    worker = AmazonBrowserWorker()
    try:
        with pytest.raises(CatalogTimeoutError):
            worker.submit("slow", lambda: time.sleep(0.2), timeout=0.01)
    finally:
        worker.close()


def test_worker_converts_unexpected_callback_errors() -> None:
    worker = AmazonBrowserWorker()
    try:
        with pytest.raises(CatalogResponseError):
            worker.submit("broken", lambda: (_ for _ in ()).throw(ValueError("boom")), timeout=1.0)
    finally:
        worker.close()


def test_provider_close_is_idempotent() -> None:
    provider = AmazonBrowserProvider()
    provider.close()
    provider.close()
