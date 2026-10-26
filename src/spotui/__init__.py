"""SpotUI application package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("spotui")
except PackageNotFoundError:  # pragma: no cover - only when running from an unbuilt tree
    __version__ = "0.1.0"

__all__ = ["__version__"]
