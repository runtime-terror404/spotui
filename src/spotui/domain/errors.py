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
