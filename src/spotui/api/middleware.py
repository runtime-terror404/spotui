"""Pure-ASGI request correlation and access logging."""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import Headers

from spotui.logging_setup import log_context

logger = logging.getLogger("spotui.request")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    """Attach a request ID to logs, request state, and the response header."""

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI callable
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        method = scope.get("method", "")
        path = scope.get("path", "")
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message) -> None:  # noqa: ANN001
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers") or [])
                if not any(key.lower() == b"x-request-id" for key, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        with log_context(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                logger.exception("unhandled error during %s %s", method, path)
                raise
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info("%s %s -> %d %.1fms", method, path, status, elapsed_ms)
