"""Logging configuration, correlation context, and secret redaction.

SpotUI logs to stderr for foreground use and to a bounded rotating file under
the XDG state directory. Every formatted record passes through the redactor so
that cookies, authorization headers, pairing codes, and sensitive query
parameters never reach a log file.
"""

from __future__ import annotations

import contextvars
import logging
import logging.handlers
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from spotui.config import LoggingSettings
from spotui.paths import Paths

REDACTED = "[REDACTED]"

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "spotui_request_id", default=None
)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "spotui_job_id", default=None
)
import_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "spotui_import_id", default=None
)

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization headers, with or without a Bearer prefix.
    (
        re.compile(
            r"(?i)\b(authorization|proxy-authorization)\b(\s*[:=]\s*)(?:bearer\s+)?[^\r\n]+"
        ),
        rf"\1\2{REDACTED}",
    ),
    # Cookie headers and cookie-like key/value pairs. Redact the whole value.
    (
        re.compile(r"(?i)\b(cookie|set-cookie)\b(\s*[:=]\s*)[^\r\n]+"),
        rf"\1\2{REDACTED}",
    ),
    # Common credential keys in text, JSON-ish structures, and env dumps.
    (
        re.compile(
            r"(?i)(\b(?:cf_clearance|clearance|session|session_token|access_token|"
            r"refresh_token|token|api[_-]?key|secret|password|passwd|credential)\b)"
            r"([\"']?)(\s*[:=]\s*)([\"']?)([^\s&,;\"']+)\4"
        ),
        rf"\1\2\3\4{REDACTED}\4",
    ),
    # Sensitive query parameters in URLs.
    (
        re.compile(
            r"(?i)([?&](?:token|code|pairing_code|clearance|access_token|"
            r"refresh_token|session|key|secret)=)[^&\s]+"
        ),
        rf"\1{REDACTED}",
    ),
    # Pairing codes are only redacted when the surrounding words identify them.
    (re.compile(r"(?i)(pairing\s+code\s*[:=]?\s*)\d{6}\b"), rf"\1{REDACTED}"),
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+"), rf"\1{REDACTED}"),
)


def redact_text(text: str) -> str:
    """Return *text* with known secret patterns replaced."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _context_suffix() -> str:
    parts = []
    for label, variable in (
        ("request_id", request_id_var),
        ("job_id", job_id_var),
        ("import_id", import_id_var),
    ):
        value = variable.get()
        if value:
            parts.append(f"{label}={value}")
    return f" [{' '.join(parts)}]" if parts else ""


class SpotUIFormatter(logging.Formatter):
    """UTC timestamps, correlation context, and redaction for every record."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s %(message)s%(spotui_context)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        stamp = datetime.fromtimestamp(record.created, tz=UTC)
        return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    def format(self, record: logging.LogRecord) -> str:
        record.spotui_context = _context_suffix()
        return redact_text(super().format(record))


@contextmanager
def log_context(
    *,
    request_id: str | None = None,
    job_id: str | None = None,
    import_id: str | None = None,
) -> Iterator[None]:
    """Attach correlation identifiers to records emitted inside the block."""
    tokens = []
    for variable, value in (
        (request_id_var, request_id),
        (job_id_var, job_id),
        (import_id_var, import_id),
    ):
        if value is not None:
            tokens.append((variable, variable.set(value)))
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def _managed_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [handler for handler in logger.handlers if getattr(handler, "_spotui_managed", False)]


def reset_logging() -> None:
    """Remove handlers installed by :func:`setup_logging` (used by tests)."""
    root = logging.getLogger()
    for handler in _managed_handlers(root):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.WARNING)


def setup_logging(settings: LoggingSettings, paths: Paths, *, console: bool = True) -> None:
    """Configure bounded console and rotating-file logging on the root logger.

    The root logger is used deliberately so that FastAPI, SQLAlchemy, and
    uvicorn records share one redacted, bounded destination. Uvicorn is started
    with ``log_config=None`` so it does not install competing handlers.
    """
    paths.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = logging.getLogger()
    reset_logging()

    formatter = SpotUIFormatter()
    root.setLevel(getattr(logging, settings.level))

    file_handler = logging.handlers.RotatingFileHandler(
        paths.log_file,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
        encoding="utf-8",
        delay=False,
    )
    file_handler.setFormatter(formatter)
    file_handler._spotui_managed = True
    root.addHandler(file_handler)
    try:
        paths.log_file.chmod(0o600)
    except OSError:
        pass

    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        console_handler._spotui_managed = True
        root.addHandler(console_handler)
