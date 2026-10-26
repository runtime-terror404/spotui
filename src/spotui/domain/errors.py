"""Application-owned errors raised by providers and services.

Messages on these exceptions are safe to show to the user. Provider adapters
log the underlying technical failure separately.
"""

from __future__ import annotations


class CatalogError(RuntimeError):
    """Base class for Amazon Music provider failures."""


class CatalogUnavailableError(CatalogError):
    """A required browser/runtime dependency is missing or unusable."""


class CatalogTimeoutError(CatalogError):
    """The provider did not respond within the bounded request window."""


class CatalogResponseError(CatalogError):
    """The provider responded, but the result could not be used."""


class InvalidSearchQueryError(ValueError):
    """The search query is empty or too long."""


class JobNotFoundError(LookupError):
    """The requested download job does not exist."""


class JobTransitionError(RuntimeError):
    """The requested job action is not valid from its current state."""


class DuplicateActiveJobError(RuntimeError):
    """Another active job already reserves this track."""


class DownloaderUnavailableError(RuntimeError):
    """The managed downloader executable or environment is unavailable."""


class QueueUnavailableError(RuntimeError):
    """The download queue service is not configured."""


class NowPlayingUnavailableError(RuntimeError):
    """The Now Playing service is not configured."""


class LibraryUnavailableError(RuntimeError):
    """The library index service is not configured."""


class ImportsUnavailableError(RuntimeError):
    """The Spotify import service is not configured."""


class ImportNotFoundError(LookupError):
    """The requested import session, source occurrence, or candidate is missing."""


class ActiveImportConflictError(RuntimeError):
    """Another import already owns the active matching slot."""


class ImportStateError(RuntimeError):
    """The requested action is not valid for the import's current state."""


class InvalidSelectionError(RuntimeError):
    """A candidate or source-track selection is invalid."""


class PairingUnavailableError(RuntimeError):
    """The trusted-device service is not configured."""


class PairingFailedError(RuntimeError):
    """The supplied pairing code is invalid."""


class PairingRateLimitedError(RuntimeError):
    """Too many failed pairing attempts were made from this or all sources."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, retry_after_seconds)


class DeviceNotFoundError(LookupError):
    """The requested paired device does not exist or is already revoked."""

