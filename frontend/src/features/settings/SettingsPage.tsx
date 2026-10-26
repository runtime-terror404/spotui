import { useState } from "react";

import { errorMessage, errorRequestId } from "../../api/errors";
import type { PairedDevice } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SectionHeading } from "../../components/ui/SectionHeading";
import { SettingsIcon } from "../../components/icons";
import { useSnackbarStore } from "../../state/snackbarStore";
import {
  useAuthStatus,
  usePairedDevices,
  usePairingInfo,
  useRevokeDevice,
} from "../auth/hooks";

function formatSeen(timestamp: number | null | undefined): string {
  if (!timestamp) {
    return "Not seen yet";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp * 1000));
}

function DeviceRow({
  device,
  onRevoke,
  busy,
}: {
  device: PairedDevice;
  onRevoke: (device: PairedDevice) => void;
  busy: boolean;
}) {
  return (
    <div className="paired-device">
      <div className="paired-device__body">
        <strong>{device.label}</strong>
        <span>{formatSeen(device.last_seen_at)}</span>
        {device.last_seen_ip ? (
          <span className="paired-device__ip">
            Last seen from {device.last_seen_ip}
          </span>
        ) : null}
      </div>
      <Button
        variant="ghost"
        className="button--danger-text"
        disabled={busy}
        onClick={() => onRevoke(device)}
      >
        Revoke
      </Button>
    </div>
  );
}

export function SettingsPage() {
  const auth = useAuthStatus();
  const local = auth.data?.local ?? false;
  const pairing = usePairingInfo(local);
  const devices = usePairedDevices(local);
  const revoke = useRevokeDevice();
  const pushSnackbar = useSnackbarStore((state) => state.push);
  const [deviceToRevoke, setDeviceToRevoke] = useState<PairedDevice | null>(
    null,
  );
  const actionError = pairing.error ?? devices.error ?? revoke.error;

  const refresh = () => {
    void pairing.refetch();
    void devices.refetch();
  };

  if (auth.isPending) {
    return (
      <div className="settings-page" aria-busy="true">
        <span className="visually-hidden">Loading settings…</span>
        <div className="skeleton skeleton--heading" aria-hidden="true" />
        <div className="skeleton skeleton--row" aria-hidden="true" />
      </div>
    );
  }

  if (auth.isError) {
    return (
      <ErrorState
        title="Could not load access settings"
        message={errorMessage(auth.error)}
        requestId={errorRequestId(auth.error)}
        onRetry={() => {
          void auth.refetch();
        }}
      />
    );
  }

  return (
    <div className="settings-page">
      <header className="settings-page__header">
        <p className="eyebrow">Application</p>
        <h1>Settings</h1>
        <p>
          Manage trusted home-network access. SpotUI never exposes device
          management or the pairing code to unpaired LAN browsers.
        </p>
      </header>

      <section className="settings-panel" aria-label="Access and pairing">
        <SectionHeading title="Access & pairing" />

        {!local ? (
          <div className="settings-note">
            <p>
              This browser is paired
              {auth.data?.device ? ` as ${auth.data.device.label}` : ""}.
              Device management and the pairing code are available only from
              the desktop host.
            </p>
          </div>
        ) : (
          <>
            <div className="settings-grid">
              <div className="settings-field">
                <span className="settings-field__label">LAN access</span>
                {auth.data?.lan_available && auth.data.lan_url ? (
                  <code>{auth.data.lan_url}</code>
                ) : (
                  <span>
                    Unavailable. Configure <code>server.trusted_subnet</code>{" "}
                    and ensure a matching interface is active.
                  </span>
                )}
              </div>
              <div className="settings-field">
                <span className="settings-field__label">Pairing code</span>
                {pairing.data ? (
                  <span
                    className="pairing-code"
                    aria-label={`Pairing code ${pairing.data.code}`}
                  >
                    {pairing.data.code}
                  </span>
                ) : pairing.isPending ? (
                  <span>Loading…</span>
                ) : (
                  <span>Unavailable</span>
                )}
              </div>
            </div>
            <div className="settings-warning" role="note">
              <strong>Plain HTTP on your trusted home network.</strong>
              <span>
                LAN traffic is not encrypted, and the persistent device cookie
                cannot use the Secure attribute in this mode. Do not forward
                this port from your router.
              </span>
            </div>
            <p className="settings-help">
              On the phone, open the LAN address and enter this six-digit code.
              The code changes each time the server restarts; paired devices
              remain valid until revoked.
            </p>
          </>
        )}

        {actionError ? (
          <div className="inline-error" role="alert">
            <p>{errorMessage(actionError)}</p>
            {errorRequestId(actionError) ? (
              <p className="inline-error__request">
                Request ID: <code>{errorRequestId(actionError)}</code>
              </p>
            ) : null}
          </div>
        ) : null}
      </section>

      {local ? (
        <section className="settings-panel" aria-label="Paired devices">
          <div className="settings-panel__heading-row">
            <SectionHeading
              title="Paired devices"
              count={devices.data?.devices.length ?? 0}
            />
            <Button
              variant="ghost"
              disabled={pairing.isFetching || devices.isFetching}
              onClick={refresh}
            >
              Refresh
            </Button>
          </div>
          {devices.isPending ? (
            <p className="settings-help">Loading paired devices…</p>
          ) : devices.data?.devices.length ? (
            <div className="paired-device-list">
              {devices.data.devices.map((device) => (
                <DeviceRow
                  key={device.id}
                  device={device}
                  busy={revoke.isPending}
                  onRevoke={setDeviceToRevoke}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<SettingsIcon />}
              title="No paired devices"
              description="Pair a phone on your trusted home network using the code above."
            />
          )}
        </section>
      ) : null}

      <ConfirmDialog
        open={deviceToRevoke !== null}
        title="Revoke this paired device?"
        message={`${deviceToRevoke?.label ?? "This device"} will need the current pairing code to reconnect.`}
        confirmLabel="Revoke device"
        destructive
        busy={revoke.isPending}
        onCancel={() => setDeviceToRevoke(null)}
        onConfirm={() => {
          if (!deviceToRevoke) {
            return;
          }
          revoke.mutate(deviceToRevoke.id, {
            onSuccess: () => {
              setDeviceToRevoke(null);
              pushSnackbar("Paired device revoked.", "info");
            },
            onError: () => setDeviceToRevoke(null),
          });
        }}
      />
    </div>
  );
}
