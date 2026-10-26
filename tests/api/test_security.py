from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI

from spotui.app import create_app
from spotui.config import AppConfig
from spotui.persistence.database import Database
from spotui.persistence.repositories.devices import PairedDeviceRepository
from spotui.runtime import ApplicationRuntime
from spotui.schemas.errors import ErrorCode
from spotui.security.cookies import DEVICE_COOKIE_NAME
from spotui.security.csrf import CSRF_HEADER
from spotui.security.pairing import PairingAttemptLimiter
from spotui.server import Listener
from spotui.services.container import ApplicationServices
from spotui.services.entity_details import EntityDetailsService
from spotui.services.search import SearchService
from spotui.services.trusted_devices import TrustedDeviceService
from tests.api.helpers import CSRFTestClient, assert_problem
from tests.fakes import FakeCatalog

LOCAL_URL = "http://127.0.0.1:8765"
LAN_HOST = "192.168.1.10"
LAN_URL = f"http://{LAN_HOST}:8765"
LAN_CLIENT = ("192.168.1.20", 50000)
OUTSIDE_CLIENT = ("10.0.0.20", 50000)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def database(migrated_database_url: str) -> Iterator[Database]:
    instance = Database.from_url(migrated_database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def lan_config(env) -> AppConfig:
    return env.config.model_copy(
        update={
            "server": env.config.server.model_copy(
                update={"trusted_subnet": "192.168.1.0/24"}
            )
        }
    )


def make_service(
    database: Database,
    *,
    code: str = "123456",
    limiter: PairingAttemptLimiter | None = None,
) -> TrustedDeviceService:
    return TrustedDeviceService(
        PairedDeviceRepository(database.session_factory),
        pairing_code=code,
        limiter=limiter,
    )


def make_app(
    env,
    database: Database,
    service: TrustedDeviceService,
    *,
    lan: bool,
) -> FastAPI:
    config = lan_config(env) if lan else env.config
    listeners = (
        (
            Listener(kind="local", host="127.0.0.1", port=8765),
            Listener(kind="lan", host=LAN_HOST, port=8765),
        )
        if lan
        else (Listener(kind="local", host="127.0.0.1", port=8765),)
    )
    runtime = ApplicationRuntime(config=config, paths=env.paths, listeners=listeners)
    catalog = FakeCatalog()
    runtime.services = ApplicationServices(
        search=SearchService(catalog),
        entity_details=EntityDetailsService(catalog),
        trusted_devices=service,
        resources=(),
    )
    return create_app(runtime, serve_frontend=False)


def test_local_auth_status_and_pairing_code_are_local_only(
    env, database: Database
) -> None:
    service = make_service(database)
    app = make_app(env, database, service, lan=True)
    with CSRFTestClient(app, base_url=LOCAL_URL) as client:
        status = client.get("/api/v1/auth/status")
        pairing = client.get("/api/v1/devices/pairing")
        devices = client.get("/api/v1/devices")

    assert status.status_code == 200
    assert status.json()["local"] is True
    assert status.json()["authenticated"] is True
    assert status.json()["pairing_required"] is False
    assert status.json()["lan_available"] is True
    assert status.json()["lan_url"] == LAN_URL
    assert "code" not in status.json()
    assert pairing.status_code == 200
    assert pairing.json() == {
        "code": "123456",
        "lan_available": True,
        "lan_url": LAN_URL,
    }
    assert devices.status_code == 200
    assert devices.json() == {"devices": []}


def test_lan_pairing_unlocks_protected_routes_without_exposing_the_code(
    env, database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    service = make_service(database)
    app = make_app(env, database, service, lan=True)
    with caplog.at_level(logging.INFO):
        with CSRFTestClient(
            app,
            base_url=LAN_URL,
            client=LAN_CLIENT,
        ) as client:
            unauthenticated = client.get("/api/v1/auth/status")
            code_attempt = client.get("/api/v1/devices/pairing")
            protected_action = client.post("/api/v1/library/scan")
            wrong = client.post(
                "/api/v1/auth/pair",
                json={"code": "000000", "label": "Phone"},
            )
            paired = client.post(
                "/api/v1/auth/pair",
                json={"code": "123456", "label": "Phone"},
            )
            authenticated = client.get("/api/v1/auth/status")
            devices = client.get("/api/v1/devices")
            lan_pairing_code = client.get("/api/v1/devices/pairing")
            cookie_headers = paired.headers.get_list("set-cookie")

    assert unauthenticated.status_code == 200
    assert unauthenticated.json()["local"] is False
    assert unauthenticated.json()["authenticated"] is False
    assert unauthenticated.json()["pairing_required"] is True
    assert "code" not in unauthenticated.json()
    assert_problem(code_attempt, 401, ErrorCode.DEVICE_UNAUTHENTICATED)
    assert "123456" not in code_attempt.text
    assert_problem(protected_action, 401, ErrorCode.DEVICE_UNAUTHENTICATED)
    assert_problem(wrong, 403, ErrorCode.PAIRING_FAILED)
    assert "123456" not in wrong.text
    assert paired.status_code == 200
    body = paired.json()
    assert body["authenticated"] is True
    assert body["local"] is False
    assert body["device"]["label"] == "Phone"
    assert "credential" not in body
    assert "123456" not in paired.text
    assert any("httponly" in header.lower() for header in cookie_headers)
    assert any("samesite=strict" in header.lower() for header in cookie_headers)
    assert not any("secure" in header.lower().replace("samesite", "") for header in cookie_headers)
    assert authenticated.status_code == 200
    assert authenticated.json()["authenticated"] is True
    assert authenticated.json()["device"]["label"] == "Phone"
    assert_problem(devices, 403, ErrorCode.FORBIDDEN)
    assert_problem(lan_pairing_code, 403, ErrorCode.FORBIDDEN)
    assert "123456" not in caplog.text


def test_host_origin_and_csrf_are_enforced(
    env, database: Database
) -> None:
    service = make_service(database)
    app = make_app(env, database, service, lan=True)
    with CSRFTestClient(
        app,
        base_url=LAN_URL,
        client=LAN_CLIENT,
    ) as client:
        invalid_host = client.get(
            "/api/v1/health",
            headers={"Host": "evil.example"},
        )
        client.headers.pop(CSRF_HEADER)
        missing_csrf = client.post(
            "/api/v1/auth/pair",
            json={"code": "123456"},
        )
        client.headers[CSRF_HEADER] = client.cookies.get("spotui_csrf")
        invalid_origin = client.post(
            "/api/v1/auth/pair",
            json={"code": "123456"},
            headers={"Origin": "https://evil.example"},
        )

    assert_problem(invalid_host, 400, ErrorCode.INVALID_HOST_ORIGIN)
    assert_problem(missing_csrf, 403, ErrorCode.CSRF_FAILED)
    assert_problem(invalid_origin, 403, ErrorCode.INVALID_HOST_ORIGIN)


def test_local_requests_also_require_csrf(env, database: Database) -> None:
    service = make_service(database)
    app = make_app(env, database, service, lan=False)
    with CSRFTestClient(app, base_url=LOCAL_URL) as client:
        client.headers.pop(CSRF_HEADER)
        response = client.post(
            "/api/v1/auth/pair",
            json={"code": "123456"},
        )

    assert_problem(response, 403, ErrorCode.CSRF_FAILED)


def test_untrusted_lan_source_is_rejected(env, database: Database) -> None:
    service = make_service(database)
    app = make_app(env, database, service, lan=True)
    with CSRFTestClient(
        app,
        base_url=LAN_URL,
        client=OUTSIDE_CLIENT,
    ) as client:
        status = client.get("/api/v1/auth/status")

    assert_problem(status, 403, ErrorCode.FORBIDDEN)


def test_pairing_rate_limit_returns_retry_after(env, database: Database) -> None:
    clock = Clock()
    limiter = PairingAttemptLimiter(
        source_limit=2,
        global_limit=10,
        clock=clock,
    )
    service = make_service(database, limiter=limiter)
    app = make_app(env, database, service, lan=True)
    with CSRFTestClient(
        app,
        base_url=LAN_URL,
        client=LAN_CLIENT,
    ) as client:
        first = client.post("/api/v1/auth/pair", json={"code": "000000"})
        second = client.post("/api/v1/auth/pair", json={"code": "000000"})
        limited = client.post("/api/v1/auth/pair", json={"code": "123456"})

    assert first.status_code == 403
    assert second.status_code == 403
    assert_problem(limited, 429, ErrorCode.RATE_LIMITED)
    assert int(limited.headers["retry-after"]) > 0


def test_paired_cookie_survives_restart_and_revocation_invalidates_it(
    env, database: Database
) -> None:
    first_service = make_service(database, code="123456")
    first_app = make_app(env, database, first_service, lan=True)
    with CSRFTestClient(
        first_app,
        base_url=LAN_URL,
        client=LAN_CLIENT,
    ) as client:
        paired = client.post(
            "/api/v1/auth/pair",
            json={"code": "123456", "label": "Phone"},
        )
        assert paired.status_code == 200
        device_id = paired.json()["device"]["id"]
        credential = client.cookies.get(DEVICE_COOKIE_NAME)
        assert credential
    assert credential not in paired.text

    second_service = make_service(database, code="654321")
    second_app = make_app(env, database, second_service, lan=True)
    with CSRFTestClient(
        second_app,
        base_url=LAN_URL,
        client=LAN_CLIENT,
        cookies={DEVICE_COOKIE_NAME: credential},
    ) as lan_client:
        status = lan_client.get("/api/v1/auth/status")
        assert status.status_code == 200
        assert status.json()["authenticated"] is True
        assert status.json()["device"]["id"] == device_id

        local_service = make_service(database, code="999999")
        local_app = make_app(env, database, local_service, lan=False)
        with CSRFTestClient(local_app, base_url=LOCAL_URL) as local_client:
            devices = local_client.get("/api/v1/devices")
            assert devices.status_code == 200
            assert devices.json()["devices"][0]["id"] == device_id
            revoked = local_client.delete(f"/api/v1/devices/{device_id}")
            assert revoked.status_code == 204

        after_revoke = lan_client.get("/api/v1/auth/status")
        assert after_revoke.status_code == 200
        assert after_revoke.json()["authenticated"] is False
        assert after_revoke.json()["pairing_required"] is True
        assert after_revoke.json()["device"] is None

    with database.session_factory() as session:
        from spotui.persistence.models import PairedDevice

        row = session.get(PairedDevice, device_id)
        assert row is not None
        assert row.revoked_at is not None
        assert credential not in row.credential_hash
