"""Typed contracts for pairing and paired-device management."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from spotui.domain.devices import PairedDevice


class PairedDeviceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    created_at: int
    last_seen_at: int | None = None
    last_seen_ip: str | None = None
    user_agent: str | None = None


class AuthStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local: bool
    authenticated: bool
    pairing_required: bool
    lan_available: bool
    lan_url: str | None = None
    device: PairedDeviceResult | None = None


class PairingInfoResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    lan_available: bool
    lan_url: str | None = None


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    label: str | None = Field(default=None, max_length=80)


class PairedDeviceListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: list[PairedDeviceResult]


def paired_device_result(device: PairedDevice) -> PairedDeviceResult:
    return PairedDeviceResult(
        id=device.id,
        label=device.label,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
        last_seen_ip=device.last_seen_ip,
        user_agent=device.user_agent,
    )
