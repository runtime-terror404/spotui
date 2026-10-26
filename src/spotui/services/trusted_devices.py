"""Pairing code, persistent browser credentials, and device revocation."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from spotui.domain.devices import PairedDevice
from spotui.domain.errors import PairingFailedError, PairingRateLimitedError
from spotui.persistence.repositories.devices import PairedDeviceRepository
from spotui.security.cookies import generate_device_token, hash_credential
from spotui.security.pairing import PairingAttemptLimiter, generate_pairing_code


@dataclass(frozen=True, slots=True)
class PairingResult:
    device: PairedDevice
    credential: str


class TrustedDeviceService:
    def __init__(
        self,
        repository: PairedDeviceRepository,
        *,
        pairing_code: str | None = None,
        limiter: PairingAttemptLimiter | None = None,
    ) -> None:
        self._repository = repository
        self._pairing_code = pairing_code or generate_pairing_code()
        self._limiter = limiter or PairingAttemptLimiter()

    @property
    def pairing_code(self) -> str:
        return self._pairing_code

    def pair(
        self,
        code: str,
        *,
        source_ip: str | None,
        user_agent: str | None,
        label: str | None = None,
    ) -> PairingResult:
        source_key = source_ip or "unknown"
        retry_after = self._limiter.retry_after(source_key)
        if retry_after:
            raise PairingRateLimitedError(
                "Too many failed pairing attempts. Try again later.",
                retry_after_seconds=retry_after,
            )
        normalized = code.strip()
        valid = (
            len(normalized) == 6
            and normalized.isdigit()
            and secrets.compare_digest(normalized, self._pairing_code)
        )
        if not valid:
            self._limiter.record_failure(source_key)
            raise PairingFailedError("The pairing code is incorrect or expired.")
        self._limiter.record_success(source_key)
        credential = generate_device_token()
        device = self._repository.create(
            hash_credential(credential),
            label=self._device_label(label, user_agent),
            source_ip=source_ip,
            user_agent=(user_agent or "")[:500] or None,
        )
        return PairingResult(device=device, credential=credential)

    def authenticate(
        self,
        credential: str | None,
        *,
        source_ip: str | None,
        user_agent: str | None,
    ) -> PairedDevice | None:
        if not credential or len(credential) > 256:
            return None
        device = self._repository.find_active_by_hash(hash_credential(credential))
        if device is None:
            return None
        return self._repository.touch(
            device.id,
            source_ip=source_ip,
            user_agent=(user_agent or "")[:500] or None,
        )

    def list_devices(self) -> tuple[PairedDevice, ...]:
        return self._repository.list_active()

    def revoke(self, device_id: str) -> PairedDevice:
        return self._repository.revoke(device_id)

    @staticmethod
    def _device_label(label: str | None, user_agent: str | None) -> str:
        cleaned = " ".join((label or "").split())[:80]
        if cleaned:
            return cleaned
        if user_agent:
            return "Paired browser"
        return "Browser device"
