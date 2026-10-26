"""Listener-aware Host/Origin, CSRF, and paired-device enforcement."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from spotui.domain.devices import PairedDevice
from spotui.runtime import ApplicationRuntime
from spotui.schemas.errors import ErrorCode
from spotui.security.cookies import (
    CSRF_COOKIE_NAME,
    DEVICE_COOKIE_NAME,
    clear_device_cookie,
    cookies_from_headers,
    csrf_cookie,
    generate_csrf_token,
)
from spotui.security.csrf import CSRF_HEADER, SAFE_METHODS, csrf_matches
from spotui.security.host_origin import (
    listener_host_allowed,
    origin_allowed,
    source_in_subnet,
)

logger = logging.getLogger("spotui.security")

_UNAUTHENTICATED_PATHS = frozenset(
    {
        "/",
        "/favicon.ico",
        "/favicon.png",
        "/api/v1/auth/status",
        "/api/v1/auth/pair",
        "/api/v1/health",
    }
)


class SecurityMiddleware:
    """Reject hostile hosts, cross-site writes, and unpaired LAN clients."""

    def __init__(self, app, *, runtime: ApplicationRuntime) -> None:  # noqa: ANN001
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        request_id = state.get("request_id") or uuid4().hex
        state.setdefault("request_id", request_id)
        headers = Headers(scope=scope)
        server = scope.get("server") or ("", 0)
        server_host, server_port = str(server[0]), int(server[1] or 0)
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        client = scope.get("client")
        source_ip = str(client[0]) if client else None
        cookie_headers = headers.getlist("cookie")
        cookies = cookies_from_headers(cookie_headers)
        csrf_token = cookies.get(CSRF_COOKIE_NAME)
        issue_csrf = not csrf_token
        if issue_csrf:
            csrf_token = generate_csrf_token()
        clear_device = False

        async def send_with_cookies(message) -> None:  # noqa: ANN001
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers") or [])
                if issue_csrf and csrf_token:
                    response_headers.append(
                        (b"set-cookie", csrf_cookie(csrf_token).encode("latin-1"))
                    )
                if clear_device:
                    response_headers.append(
                        (b"set-cookie", clear_device_cookie().encode("latin-1"))
                    )
                if path.startswith(("/api/v1/auth", "/api/v1/devices")):
                    response_headers.append((b"cache-control", b"no-store"))
                message["headers"] = response_headers
            await send(message)

        if not listener_host_allowed(
            headers.get("host", ""),
            server_host=server_host,
            server_port=server_port,
        ):
            await self._reject(
                scope,
                send_with_cookies,
                request_id=request_id,
                status_code=400,
                code=ErrorCode.INVALID_HOST_ORIGIN,
                title="Invalid Host header",
                detail="This server address is not allowed.",
            )
            return

        local = self._is_local_listener(server_host, server_port)
        if not local:
            trusted_subnet = self.runtime.config.server.trusted_subnet
            if not trusted_subnet or not source_in_subnet(source_ip, trusted_subnet):
                logger.warning(
                    "rejected request from untrusted source %s for %s",
                    source_ip,
                    path,
                )
                await self._reject(
                    scope,
                    send_with_cookies,
                    request_id=request_id,
                    status_code=403,
                    code=ErrorCode.FORBIDDEN,
                    title="Untrusted network",
                    detail="Requests are limited to the configured trusted home subnet.",
                )
                return

        if method not in SAFE_METHODS:
            origin = headers.get("origin")
            if not origin_allowed(
                origin,
                server_host=server_host,
                server_port=server_port,
                request_scheme=scope.get("scheme", "http"),
            ):
                await self._reject(
                    scope,
                    send_with_cookies,
                    request_id=request_id,
                    status_code=403,
                    code=ErrorCode.INVALID_HOST_ORIGIN,
                    title="Invalid Origin",
                    detail="The request origin is not allowed.",
                )
                return
            if not csrf_matches(csrf_token if not issue_csrf else None, headers.get(CSRF_HEADER)):
                await self._reject(
                    scope,
                    send_with_cookies,
                    request_id=request_id,
                    status_code=403,
                    code=ErrorCode.CSRF_FAILED,
                    title="CSRF check failed",
                    detail="Refresh the page and try again.",
                )
                return

        device: PairedDevice | None = None
        authenticated = local
        if not local:
            credentials = cookies.get(DEVICE_COOKIE_NAME)
            if credentials:
                service = (
                    self.runtime.services.trusted_devices
                    if self.runtime.services is not None
                    else None
                )
                if service is not None:
                    device = await run_in_threadpool(
                        service.authenticate,
                        credentials,
                        source_ip=source_ip,
                        user_agent=headers.get("user-agent"),
                    )
                authenticated = device is not None
                if device is None and path != "/api/v1/auth/pair":
                    clear_device = True
            if not authenticated and path not in _UNAUTHENTICATED_PATHS and not path.startswith(
                "/assets/"
            ):
                await self._reject(
                    scope,
                    send_with_cookies,
                    request_id=request_id,
                    status_code=401,
                    code=ErrorCode.DEVICE_UNAUTHENTICATED,
                    title="Pairing required",
                    detail="This browser is not paired with SpotUI.",
                )
                return

        state["spotui_local"] = local
        state["spotui_authenticated"] = authenticated
        state["spotui_device"] = device
        state["spotui_source_ip"] = source_ip
        await self.app(scope, receive, send_with_cookies)

    def _is_local_listener(self, server_host: str, server_port: int) -> bool:
        local_match = any(
            listener.kind == "local"
            and listener.host == server_host
            and listener.port == server_port
            for listener in self.runtime.listeners
        )
        if local_match:
            return True
        lan_match = any(
            listener.kind == "lan"
            and listener.host == server_host
            and listener.port == server_port
            for listener in self.runtime.listeners
        )
        if lan_match:
            return False
        # Tests and embedded ASGI clients often use a synthetic host. Fail
        # closed once any LAN listener exists; otherwise the app is loopback-only.
        return not any(listener.kind == "lan" for listener in self.runtime.listeners)

    async def _reject(
        self,
        scope,
        send,  # noqa: ANN001
        *,
        request_id: str,
        status_code: int,
        code: ErrorCode,
        title: str,
        detail: str,
    ) -> None:
        body = {
            "type": f"urn:spotui:error:{code.value}",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": scope.get("path", "/"),
            "code": code.value,
            "request_id": request_id,
        }
        payload = json.dumps(body).encode("utf-8")
        headers = [
            (b"content-type", b"application/problem+json"),
            (b"x-request-id", request_id.encode("ascii")),
            (b"content-length", str(len(payload)).encode("ascii")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": payload})
