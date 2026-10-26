"""IPv4 interface discovery for trusted-subnet LAN listening.

LAN access is bound to one concrete local IPv4 address inside the configured
trusted subnet. SpotUI never binds a wildcard address.
"""

from __future__ import annotations

import fcntl
import ipaddress
import socket
import struct
from collections.abc import Mapping, Sequence

_SIOCGIFADDR = 0x8915


def ipv4_interfaces() -> dict[str, list[str]]:
    """Return active Linux interface IPv4 addresses (one per interface).

    Uses ``SIOCGIFADDR`` from the standard library rather than shelling out to
    ``ip``. Interfaces without an IPv4 address are omitted.
    """
    addresses: dict[str, list[str]] = {}
    try:
        names = [name for _, name in socket.if_nameindex()]
    except OSError:
        return addresses

    for name in names:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                request = struct.pack("256s", name.encode("utf-8")[:15])
                response = fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, request)
            addresses[name] = [socket.inet_ntoa(response[20:24])]
        except OSError:
            continue
    return addresses


def find_lan_address(
    cidr: str,
    *,
    interfaces: Mapping[str, Sequence[str]] | None = None,
) -> str | None:
    """Return a deterministic non-loopback address inside *cidr*, if any.

    ``interfaces`` exists for tests and dependency injection. Production calls
    :func:`ipv4_interfaces`.
    """
    network = ipaddress.ip_network(cidr, strict=False)
    if network.version != 4:
        return None

    candidates: list[tuple[str, str]] = []
    source = ipv4_interfaces() if interfaces is None else interfaces
    for interface_name, raw_addresses in source.items():
        for raw_address in raw_addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError:
                continue
            if address.version != 4:
                continue
            if (
                address.is_loopback
                or address.is_link_local
                or address.is_unspecified
                or address.is_multicast
            ):
                continue
            if address in network:
                candidates.append((interface_name, str(address)))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]
