from __future__ import annotations

import socket

import pytest

from spotui.config import AppConfig, ServerSettings
from spotui.server import (
    Listener,
    PortUnavailableError,
    bind_listeners,
    close_listeners,
    listener_specs,
)


def _config(**server_values) -> AppConfig:
    return AppConfig(server=ServerSettings(**server_values))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_listener_is_loopback_only_without_trusted_subnet() -> None:
    specs = listener_specs(_config(port=8765))

    assert len(specs) == 1
    assert specs[0].kind == "local"
    assert specs[0].host == "127.0.0.1"
    assert specs[0].port == 8765
    assert specs[0].url == "http://127.0.0.1:8765"


def test_lan_listener_uses_matching_interface_and_same_port() -> None:
    config = _config(port=9000, trusted_subnet="192.168.1.0/24")

    specs = listener_specs(
        config,
        interfaces={"lo": ["127.0.0.1"], "wlan0": ["192.168.1.42"]},
    )

    assert [spec.kind for spec in specs] == ["local", "lan"]
    assert specs[1].host == "192.168.1.42"
    assert specs[1].port == 9000
    assert specs[1].url == "http://192.168.1.42:9000"


def test_no_lan_listener_when_no_interface_matches() -> None:
    config = _config(trusted_subnet="192.168.1.0/24")

    specs = listener_specs(config, interfaces={"wlan0": ["10.0.0.9"]})

    assert len(specs) == 1
    assert specs[0].kind == "local"


def test_listeners_never_use_wildcard_hosts() -> None:
    config = _config(trusted_subnet="0.0.0.0/0")

    specs = listener_specs(
        config,
        interfaces={"eth0": ["192.168.1.5"], "lo": ["127.0.0.1"]},
    )

    assert all(spec.host not in ("0.0.0.0", "::", "") for spec in specs)


def test_listener_rejects_wildcard_and_invalid_ports() -> None:
    with pytest.raises(ValueError, match="wildcard"):
        Listener(kind="local", host="0.0.0.0", port=8765)
    with pytest.raises(ValueError, match="port"):
        Listener(kind="local", host="127.0.0.1", port=0)


def test_bind_and_close_listener() -> None:
    port = free_port()
    listener = Listener(kind="local", host="127.0.0.1", port=port)

    sockets = bind_listeners([listener])
    try:
        assert sockets[0].getsockname()[:2] == ("127.0.0.1", port)
    finally:
        close_listeners(sockets)


def test_port_collision_is_reported_clearly() -> None:
    port = free_port()
    listener = Listener(kind="local", host="127.0.0.1", port=port)
    sockets = bind_listeners([listener])
    try:
        with pytest.raises(PortUnavailableError, match=rf"127\.0\.0\.1:{port}"):
            bind_listeners([listener])
    finally:
        close_listeners(sockets)


def test_two_concrete_addresses_can_share_a_port() -> None:
    port = free_port()
    local = Listener(kind="local", host="127.0.0.1", port=port)
    stand_in_lan = Listener(kind="lan", host="127.0.0.2", port=port)

    sockets = bind_listeners([local, stand_in_lan])
    try:
        assert {sock.getsockname()[0] for sock in sockets} == {"127.0.0.1", "127.0.0.2"}
    finally:
        close_listeners(sockets)
