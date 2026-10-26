"""Listener planning, socket binding, and the uvicorn runner.

SpotUI always binds loopback. A second listener is added only when a trusted
subnet is configured and an active IPv4 interface address matches it. Both
sockets are served by one uvicorn ``Server`` so the process has one lifespan,
one worker, and one database pool. The wildcard address is never used.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import uvicorn

from spotui.config import AppConfig
from spotui.security.subnet import find_lan_address

ListenerKind = Literal["local", "lan"]
_WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", ""})


@dataclass(frozen=True, slots=True)
class Listener:
    kind: ListenerKind
    host: str
    port: int

    def __post_init__(self) -> None:
        if self.kind not in ("local", "lan"):
            raise ValueError(f"unknown listener kind {self.kind!r}")
        if not self.host or self.host in _WILDCARD_HOSTS:
            raise ValueError("SpotUI never binds a wildcard address")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"invalid listener port {self.port}")

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class PortUnavailableError(RuntimeError):
    """A requested listener address could not be bound."""

    def __init__(self, listener: Listener, error: OSError) -> None:
        self.listener = listener
        self.error = error
        reason = os.strerror(error.errno) if error.errno else str(error)
        super().__init__(
            f"cannot listen on {listener.host}:{listener.port}: {reason}. "
            "Check the configured port and stop any process already using it."
        )


def listener_specs(
    config: AppConfig,
    *,
    interfaces: Mapping[str, Sequence[str]] | None = None,
) -> tuple[Listener, ...]:
    """Plan the concrete listeners for this configuration."""
    port = config.server.port
    listeners = [Listener(kind="local", host="127.0.0.1", port=port)]
    if config.server.trusted_subnet:
        lan_address = find_lan_address(
            config.server.trusted_subnet,
            interfaces=interfaces,
        )
        if lan_address:
            listeners.append(Listener(kind="lan", host=lan_address, port=port))
    return tuple(listeners)


def bind_listeners(listeners: Iterable[Listener]) -> list[socket.socket]:
    """Bind and listen on every listener, or close all and fail clearly."""
    bound: list[socket.socket] = []
    for listener in listeners:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((listener.host, listener.port))
            sock.listen(2048)
            sock.setblocking(False)
        except OSError as exc:
            sock.close()
            close_listeners(bound)
            raise PortUnavailableError(listener, exc) from exc
        bound.append(sock)
    return bound


def close_listeners(sockets: Iterable[socket.socket]) -> None:
    for sock in sockets:
        try:
            sock.close()
        except OSError:
            pass


def run_server(app, sockets: list[socket.socket], config: AppConfig) -> uvicorn.Server:
    """Serve the application on the already-bound sockets.

    ``log_config=None`` keeps uvicorn from installing handlers that bypass
    SpotUI's redaction and rotation. Access logging comes from SpotUI's request
    middleware instead.
    """
    server_config = uvicorn.Config(
        app,
        log_config=None,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        lifespan="on",
        timeout_graceful_shutdown=max(0, int(config.server.shutdown_grace_seconds)),
    )
    server = uvicorn.Server(server_config)
    server.run(sockets=sockets)
    return server
