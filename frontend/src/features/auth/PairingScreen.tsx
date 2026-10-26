import { useId, useState } from "react";

import logoUrl from "../../assets/logo.png";
import { errorMessage, errorRequestId } from "../../api/errors";
import type { AuthStatus } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { usePairBrowser } from "./hooks";

export function PairingScreen({ status }: { status: AuthStatus }) {
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const pair = usePairBrowser();
  const codeId = useId();
  const labelId = useId();
  const hintId = useId();

  return (
    <main className="pairing-screen">
      <section className="pairing-card" aria-labelledby="pairing-title">
        <div className="pairing-card__brand" aria-hidden="true">
          <img className="brand-mark" src={logoUrl} alt="" />
        </div>
        <p className="eyebrow">Trusted home network</p>
        <h1 id="pairing-title">Pair this browser</h1>
        <p className="pairing-card__intro">
          Enter the six-digit code shown in Settings on the SpotUI desktop.
          {status.lan_url ? (
            <>
              {" "}
              This device reached <code>{status.lan_url}</code>.
            </>
          ) : null}
        </p>
        <div className="pairing-card__warning" role="note">
          <strong>Use only your trusted home Wi-Fi.</strong>
          <span>
            LAN traffic uses plain HTTP and is not encrypted. Do not expose
            SpotUI through router port forwarding.
          </span>
        </div>
        <form
          className="pairing-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!/^\d{6}$/.test(code)) {
              return;
            }
            pair.mutate({
              code,
              label: label.trim() || undefined,
            });
          }}
        >
          <label htmlFor={codeId}>Six-digit pairing code</label>
          <input
            id={codeId}
            value={code}
            onChange={(event) => {
              setCode(event.target.value.replace(/\D/g, "").slice(0, 6));
            }}
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            autoComplete="one-time-code"
            aria-describedby={hintId}
            className="pairing-code-input"
            autoFocus
            required
          />
          <label htmlFor={labelId}>Device name (optional)</label>
          <input
            id={labelId}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            maxLength={80}
            autoComplete="off"
            placeholder="For example, My phone"
          />
          <Button
            type="submit"
            variant="primary"
            disabled={code.length !== 6 || pair.isPending}
          >
            {pair.isPending ? "Pairing…" : "Pair browser"}
          </Button>
        </form>
        <p id={hintId} className="pairing-card__hint">
          The code changes whenever the SpotUI server restarts. This browser
          stays paired until it is revoked from the desktop.
        </p>
        {pair.isError ? (
          <div className="inline-error" role="alert">
            <p>{errorMessage(pair.error)}</p>
            {errorRequestId(pair.error) ? (
              <p className="inline-error__request">
                Request ID: <code>{errorRequestId(pair.error)}</code>
              </p>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
