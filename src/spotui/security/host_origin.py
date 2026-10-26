"""Host and Origin validation for loopback and trusted-LAN listeners."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def listener_host_allowed(host_header: str, *, server_host: str, server_port: int) -> bool:
    if not host_header or "," in host_header:
        return False
    try:
        parsed = urlsplit(f"//{host_header}")
        host = (parsed.hostname or "").casefold().rstrip(".")
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        return False
    if not host or parsed.username or parsed.password:
        return False
    allowed = {server_host.casefold().rstrip(".")}
    server_address = _ip_address(server_host)
    if server_address is not None and server_address.is_loopback:
        allowed.update({"127.0.0.1", "localhost"})
    return host in allowed and port == server_port


def origin_allowed(
    origin: str | None,
    *,
    server_host: str,
    server_port: int,
    request_scheme: str,
) -> bool:
    if origin is None:
        return True
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != request_scheme
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        return False
    effective_port = port if port is not None else 80
    return listener_host_allowed(
        f"{parsed.hostname}:{effective_port}",
        server_host=server_host,
        server_port=server_port,
    )


def source_in_subnet(source_host: str | None, cidr: str) -> bool:
    if not source_host:
        return False
    try:
        address = ipaddress.ip_address(source_host)
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return address.version == network.version and address in network


def _ip_address(value: str):
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None
