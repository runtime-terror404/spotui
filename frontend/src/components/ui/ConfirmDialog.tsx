import { useEffect, useId, useRef } from "react";

import { Button } from "./Button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  destructive?: boolean;
  busy?: boolean;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  destructive = false,
  busy = false,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const messageId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-labelledby={titleId}
      aria-describedby={messageId}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          onCancel();
        }
      }}
    >
      <div className="confirm-dialog__body">
        <h2 id={titleId}>{title}</h2>
        <p id={messageId}>{message}</p>
        <div className="confirm-dialog__actions">
          <Button variant="secondary" autoFocus disabled={busy} onClick={onCancel}>
            Keep it
          </Button>
          <Button
            variant={destructive ? "primary" : "secondary"}
            className={destructive ? "button--danger" : ""}
            disabled={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
