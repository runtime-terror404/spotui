import type { ReactNode } from "react";

import { errorMessage, errorRequestId } from "../../api/errors";
import { ErrorState } from "../../components/ui/ErrorState";
import { PairingScreen } from "./PairingScreen";
import { useAuthStatus } from "./hooks";

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuthStatus();

  if (auth.isPending) {
    return (
      <main className="auth-screen" aria-busy="true">
        <span className="visually-hidden">Checking SpotUI access…</span>
        <div className="skeleton skeleton--heading" aria-hidden="true" />
      </main>
    );
  }

  if (auth.isError) {
    return (
      <main className="auth-screen">
        <ErrorState
          title="Could not check SpotUI access"
          message={errorMessage(auth.error)}
          requestId={errorRequestId(auth.error)}
          onRetry={() => {
            void auth.refetch();
          }}
        />
      </main>
    );
  }

  if (auth.data.pairing_required) {
    return <PairingScreen status={auth.data} />;
  }

  return children;
}
