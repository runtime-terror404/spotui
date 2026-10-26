from __future__ import annotations

import ipaddress

from spotui.security.subnet import find_lan_address


def test_finds_matching_non_loopback_address() -> None:
    interfaces = {
        "lo": ["127.0.0.1"],
        "wlan0": ["192.168.1.24"],
        "docker0": ["172.17.0.1"],
    }

    assert find_lan_address("192.168.1.0/24", interfaces=interfaces) == "192.168.1.24"


def test_ignores_loopback_link_local_and_outside_addresses() -> None:
    interfaces = {
        "lo": ["127.0.0.1"],
        "eth0": ["169.254.10.20", "10.0.0.5"],
        "wlan0": ["192.168.50.7"],
    }

    assert find_lan_address("192.168.1.0/24", interfaces=interfaces) is None


def test_returns_none_for_ipv6_network() -> None:
    interfaces = {"wlan0": ["192.168.1.24"]}

    assert find_lan_address("fd00::/64", interfaces=interfaces) is None


def test_choice_is_deterministic_when_multiple_interfaces_match() -> None:
    interfaces = {
        "wlan1": ["192.168.1.30"],
        "wlan0": ["192.168.1.20"],
    }

    assert find_lan_address("192.168.1.0/24", interfaces=interfaces) == "192.168.1.20"


def test_empty_interfaces_returns_none() -> None:
    assert find_lan_address("192.168.1.0/24", interfaces={}) is None


def test_accepts_cidr_with_host_bits() -> None:
    assert find_lan_address("192.168.1.40/24", interfaces={"wlan0": ["192.168.1.40"]}) == (
        "192.168.1.40"
    )


def test_never_returns_loopback_even_if_subnet_covers_it() -> None:
    interfaces = {"lo": ["127.0.0.5"], "wlan0": ["127.0.0.6"]}
    network = ipaddress.ip_network("127.0.0.0/8")

    assert find_lan_address(str(network), interfaces=interfaces) is None
