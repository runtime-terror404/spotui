"""Cookie construction and parsing for pairing and CSRF credentials.

LAN mode uses plain HTTP on a trusted home network. The device cookie therefore
cannot set ``Secure`` without breaking authentication; transport is explicitly
unencrypted and the LAN restriction is part of the security boundary.
"""

from __future__ import annotations

import hashlib
import secrets
from http.cookies import CookieError, SimpleCookie

DEVICE_COOKIE_NAME = "spotui_device"
CSRF_COOKIE_NAME = "spotui_csrf"
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def hash_credential(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def cookies_from_headers(cookie_headers: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for header in cookie_headers:
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except CookieError:
            continue
        for name, morsel in cookie.items():
            values[name] = morsel.value
    return values


def device_cookie(token: str) -> str:
    return (
        f"{DEVICE_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; "
        f"Max-Age={COOKIE_MAX_AGE_SECONDS}"
    )


def clear_device_cookie() -> str:
    return (
        f"{DEVICE_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
    )


def csrf_cookie(token: str) -> str:
    return (
        f"{CSRF_COOKIE_NAME}={token}; Path=/; SameSite=Strict; "
        f"Max-Age={COOKIE_MAX_AGE_SECONDS}"
    )
