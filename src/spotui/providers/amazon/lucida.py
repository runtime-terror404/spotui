"""Album and editorial-playlist resolution through the managed lucidadl env."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from spotui.domain.catalog import EntityDetail
from spotui.domain.errors import (
    CatalogResponseError,
    CatalogTimeoutError,
    CatalogUnavailableError,
)
from spotui.providers.amazon.parsing import parse_lucida_info

logger = logging.getLogger("spotui.amazon.lucida")

_MAX_RESOLVER_OUTPUT = 2_000_000
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _safe_bridge_error(stderr: str) -> str:
    lines = [line for line in stderr.splitlines() if line.strip()]
    if lines:
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = payload.get("error")
            if isinstance(message, str) and message.strip():
                return message.strip()[:300]
    return "The Amazon catalog resolver failed."


class LucidaDetailProvider:
    """Resolve albums/editorial playlists without importing lucidadl in-process."""

    def __init__(
        self,
        python_executable: Path,
        *,
        script_path: Path | None = None,
        runner: Runner = subprocess.run,
        timeout: float = 120.0,
    ) -> None:
        self._python = python_executable
        self._script = script_path or Path(__file__).with_name("lucida_bridge.py")
        self._runner = runner
        self._timeout = timeout

    def resolve(self, url: str) -> EntityDetail:
        if not (self._python.is_file() and os.access(self._python, os.X_OK)):
            raise CatalogUnavailableError(
                "The managed lucidadl environment is missing. Run 'spotui deps install'."
            )
        if not self._script.is_file():
            raise CatalogUnavailableError(
                "The Amazon catalog resolver is missing from this installation."
            )

        command: Sequence[str] = [str(self._python), str(self._script), url]
        try:
            result = self._runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CatalogTimeoutError("Amazon catalog resolution timed out.") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("catalog resolver could not start", exc_info=True)
            raise CatalogUnavailableError(
                "The Amazon catalog resolver could not start."
            ) from exc

        if result.returncode != 0:
            message = _safe_bridge_error(result.stderr or "")
            logger.warning("catalog resolver failed: %s", message)
            raise CatalogUnavailableError(message)
        if len(result.stdout.encode("utf-8", "replace")) > _MAX_RESOLVER_OUTPUT:
            raise CatalogResponseError("The Amazon catalog resolver returned too much data.")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CatalogResponseError(
                "The Amazon catalog resolver returned invalid data."
            ) from exc
        return parse_lucida_info(payload)
