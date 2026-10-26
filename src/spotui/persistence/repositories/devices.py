"""Persistent trusted-device credentials and revocation state."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from spotui.domain.devices import PairedDevice
from spotui.domain.errors import DeviceNotFoundError
from spotui.persistence.models import PairedDevice as PairedDeviceRow


def _epoch() -> int:
    return int(time.time())


def _to_device(row: PairedDeviceRow) -> PairedDevice:
    return PairedDevice(
        id=row.id,
        label=row.label,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        last_seen_ip=row.last_seen_ip,
        user_agent=row.user_agent,
        revoked_at=row.revoked_at,
    )


class PairedDeviceRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], int] = _epoch,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def create(
        self,
        credential_hash: str,
        *,
        label: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> PairedDevice:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = PairedDeviceRow(
                id=uuid.uuid4().hex,
                credential_hash=credential_hash,
                label=label,
                created_at=now,
                last_seen_at=now,
                last_seen_ip=source_ip,
                user_agent=user_agent,
                revoked_at=None,
            )
            session.add(row)
            session.flush()
            return _to_device(row)

    def find_active_by_hash(self, credential_hash: str) -> PairedDevice | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(PairedDeviceRow).where(
                    PairedDeviceRow.credential_hash == credential_hash,
                    PairedDeviceRow.revoked_at.is_(None),
                )
            )
            return _to_device(row) if row is not None else None

    def touch(
        self,
        device_id: str,
        *,
        source_ip: str | None,
        user_agent: str | None,
        minimum_interval_seconds: int = 60,
    ) -> PairedDevice | None:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = session.get(PairedDeviceRow, device_id)
            if row is None or row.revoked_at is not None:
                return None
            if (
                row.last_seen_at is None
                or now - row.last_seen_at >= minimum_interval_seconds
            ):
                row.last_seen_at = now
                row.last_seen_ip = source_ip
                row.user_agent = user_agent
                return _to_device(row)
            return _to_device(row)

    def list_active(self) -> tuple[PairedDevice, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(PairedDeviceRow)
                .where(PairedDeviceRow.revoked_at.is_(None))
                .order_by(PairedDeviceRow.created_at.desc(), PairedDeviceRow.id.desc())
            ).all()
            return tuple(_to_device(row) for row in rows)

    def revoke(self, device_id: str) -> PairedDevice:
        now = self._clock()
        with self._session_factory.begin() as session:
            row = session.get(PairedDeviceRow, device_id)
            if row is None:
                raise DeviceNotFoundError("Paired device not found.")
            if row.revoked_at is None:
                row.revoked_at = now
            return _to_device(row)
