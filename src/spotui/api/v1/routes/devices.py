from __future__ import annotations

from fastapi import APIRouter, Request, Response

from spotui.api.v1.dependencies import (
    LocalAccessDependency,
    TrustedDeviceDependency,
)
from spotui.schemas.devices import (
    AuthStatusResult,
    PairedDeviceListResult,
    PairingInfoResult,
    PairRequest,
    paired_device_result,
)
from spotui.security.cookies import device_cookie

router = APIRouter()


def _lan_url(request: Request) -> str | None:
    runtime = request.app.state.runtime
    for listener in runtime.listeners:
        if listener.kind == "lan":
            return listener.url
    return None


def _auth_status(request: Request) -> AuthStatusResult:
    local = bool(getattr(request.state, "spotui_local", False))
    device = getattr(request.state, "spotui_device", None)
    lan_url = _lan_url(request)
    return AuthStatusResult(
        local=local,
        authenticated=local or device is not None,
        pairing_required=not local and device is None,
        lan_available=lan_url is not None,
        lan_url=lan_url,
        device=paired_device_result(device) if device is not None else None,
    )


@router.get(
    "/auth/status",
    response_model=AuthStatusResult,
    summary="Read local/LAN authentication state without exposing the pairing code",
)
def auth_status(request: Request) -> AuthStatusResult:
    return _auth_status(request)


@router.post(
    "/auth/pair",
    response_model=AuthStatusResult,
    summary="Pair a LAN browser with the current six-digit code",
)
def pair_browser(
    request: Request,
    body: PairRequest,
    response: Response,
    devices: TrustedDeviceDependency,
) -> AuthStatusResult:
    result = devices.pair(
        body.code,
        source_ip=getattr(request.state, "spotui_source_ip", None),
        user_agent=request.headers.get("user-agent"),
        label=body.label,
    )
    response.headers.append("set-cookie", device_cookie(result.credential))
    lan_url = _lan_url(request)
    return AuthStatusResult(
        local=bool(getattr(request.state, "spotui_local", False)),
        authenticated=True,
        pairing_required=False,
        lan_available=lan_url is not None,
        lan_url=lan_url,
        device=paired_device_result(result.device),
    )


@router.get(
    "/devices/pairing",
    response_model=PairingInfoResult,
    summary="Read the per-start pairing code from the desktop host only",
)
def pairing_info(
    request: Request,
    _local: LocalAccessDependency,
    devices: TrustedDeviceDependency,
) -> PairingInfoResult:
    lan_url = _lan_url(request)
    return PairingInfoResult(
        code=devices.pairing_code,
        lan_available=lan_url is not None,
        lan_url=lan_url,
    )


@router.get(
    "/devices",
    response_model=PairedDeviceListResult,
    summary="List paired devices from the desktop host",
)
def list_devices(
    _local: LocalAccessDependency,
    devices: TrustedDeviceDependency,
) -> PairedDeviceListResult:
    return PairedDeviceListResult(
        devices=[paired_device_result(device) for device in devices.list_devices()]
    )


@router.delete(
    "/devices/{device_id}",
    status_code=204,
    summary="Revoke a paired device from the desktop host",
)
def revoke_device(
    device_id: str,
    _local: LocalAccessDependency,
    devices: TrustedDeviceDependency,
) -> Response:
    devices.revoke(device_id)
    return Response(status_code=204)
