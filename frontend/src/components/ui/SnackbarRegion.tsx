import { useEffect } from "react";

import {
  useSnackbarStore,
  type SnackbarMessage,
} from "../../state/snackbarStore";
import { CloseIcon } from "../icons";

function SnackbarItem({ item }: { item: SnackbarMessage }) {
  const dismiss = useSnackbarStore((state) => state.dismiss);

  useEffect(() => {
    const timer = window.setTimeout(() => dismiss(item.id), 3600);
    return () => window.clearTimeout(timer);
  }, [dismiss, item.id]);

  return (
    <div className={`snackbar snackbar--${item.tone}`}>
      <span>{item.message}</span>
      <button
        type="button"
        className="snackbar__close"
        aria-label="Dismiss notification"
        onClick={() => dismiss(item.id)}
      >
        <CloseIcon />
      </button>
    </div>
  );
}

export function SnackbarRegion() {
  const messages = useSnackbarStore((state) => state.messages);

  return (
    <div className="snackbar-region" role="status" aria-live="polite">
      {messages.map((item) => (
        <SnackbarItem key={item.id} item={item} />
      ))}
    </div>
  );
}
