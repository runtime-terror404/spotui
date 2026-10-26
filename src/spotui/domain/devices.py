"""Paired-device metadata exposed to the trusted desktop UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PairedDevice:
    id: str
    label: str
    created_at: int
    last_seen_at: int | None
    last_seen_ip: str | None
    user_agent: str | None
    revoked_at: int | None
