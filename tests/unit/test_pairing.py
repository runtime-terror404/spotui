from __future__ import annotations

import re
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from spotui.domain.errors import (
    DeviceNotFoundError,
    PairingFailedError,
    PairingRateLimitedError,
)
from spotui.persistence.database import Database
from spotui.persistence.models import PairedDevice as PairedDeviceRow
from spotui.persistence.repositories.devices import PairedDeviceRepository
from spotui.security.pairing import PairingAttemptLimiter, generate_pairing_code
from spotui.services.trusted_devices import TrustedDeviceService


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@dataclass
class EpochClock:
    now: int = 1_700_000_000

    def __call__(self) -> int:
        return self.now


@pytest.fixture
def database(migrated_database_url: str):
    instance = Database.from_url(migrated_database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def test_pairing_code_is_six_digits() -> None:
    assert all(re.fullmatch(r"\d{6}", generate_pairing_code()) for _ in range(20))


def test_attempt_limiter_locks_source_and_global_windows() -> None:
    clock = Clock()
    limiter = PairingAttemptLimiter(
        source_limit=2,
        global_limit=3,
        window_seconds=60,
        lockout_seconds=120,
        clock=clock,
    )

    limiter.record_failure("192.168.1.20")
    assert limiter.retry_after("192.168.1.20") == 0
    limiter.record_failure("192.168.1.20")
    assert limiter.retry_after("192.168.1.20") == 120
    assert limiter.retry_after("192.168.1.21") == 0

    clock.now += 121
    assert limiter.retry_after("192.168.1.20") == 0

    limiter.record_failure("192.168.1.21")
    limiter.record_failure("192.168.1.22")
    limiter.record_failure("192.168.1.23")
    assert limiter.retry_after("192.168.1.30") == 120


def test_success_clears_only_that_source() -> None:
    clock = Clock()
    limiter = PairingAttemptLimiter(
        source_limit=2,
        global_limit=10,
        window_seconds=60,
        lockout_seconds=120,
        clock=clock,
    )
    limiter.record_failure("192.168.1.20")
    limiter.record_success("192.168.1.20")
    limiter.record_failure("192.168.1.20")

    assert limiter.retry_after("192.168.1.20") == 0


def test_pairing_stores_only_a_credential_hash_and_supports_revocation(
    database: Database,
) -> None:
    repository = PairedDeviceRepository(database.session_factory, clock=EpochClock())
    limiter = PairingAttemptLimiter(clock=Clock())
    service = TrustedDeviceService(
        repository,
        pairing_code="123456",
        limiter=limiter,
    )

    result = service.pair(
        "123456",
        source_ip="192.168.1.20",
        user_agent="Browser UA",
        label="  My Phone  ",
    )

    assert result.device.label == "My Phone"
    assert result.device.last_seen_ip == "192.168.1.20"
    with database.session_factory() as session:
        row = session.scalar(
            select(PairedDeviceRow).where(PairedDeviceRow.id == result.device.id)
        )
        assert row is not None
        assert row.credential_hash != result.credential
        assert len(row.credential_hash) == 64
        assert result.credential not in row.credential_hash

    authenticated = service.authenticate(
        result.credential,
        source_ip="192.168.1.21",
        user_agent="Other UA",
    )
    assert authenticated is not None
    assert authenticated.id == result.device.id

    service.revoke(result.device.id)
    assert service.authenticate(
        result.credential,
        source_ip="192.168.1.21",
        user_agent="Other UA",
    ) is None
    with pytest.raises(DeviceNotFoundError):
        service.revoke("missing-device")


def test_wrong_code_and_rate_limit(database: Database) -> None:
    clock = Clock()
    repository = PairedDeviceRepository(database.session_factory)
    limiter = PairingAttemptLimiter(
        source_limit=2,
        global_limit=10,
        window_seconds=60,
        lockout_seconds=120,
        clock=clock,
    )
    service = TrustedDeviceService(
        repository,
        pairing_code="123456",
        limiter=limiter,
    )

    with pytest.raises(PairingFailedError):
        service.pair("000000", source_ip="192.168.1.20", user_agent=None)
    with pytest.raises(PairingFailedError):
        service.pair("111111", source_ip="192.168.1.20", user_agent=None)
    with pytest.raises(PairingRateLimitedError) as error:
        service.pair("123456", source_ip="192.168.1.20", user_agent=None)
    assert error.value.retry_after_seconds == 120


def test_pairing_codes_are_generated_per_service(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    codes = iter(("111111", "222222"))
    monkeypatch.setattr(
        "spotui.services.trusted_devices.generate_pairing_code",
        lambda: next(codes),
    )
    repository = PairedDeviceRepository(database.session_factory)
    first = TrustedDeviceService(repository)
    second = TrustedDeviceService(repository)

    assert first.pairing_code == "111111"
    assert second.pairing_code == "222222"
