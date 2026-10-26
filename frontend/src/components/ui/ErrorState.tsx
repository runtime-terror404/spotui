import { AlertIcon } from "../icons";
import { Button } from "./Button";

interface ErrorStateProps {
  title: string;
  message: string;
  requestId?: string;
  onRetry?: () => void;
  onBack?: () => void;
}

export function ErrorState({
  title,
  message,
  requestId,
  onRetry,
  onBack,
}: ErrorStateProps) {
  return (
    <div className="error-state" role="alert">
      <div className="error-state__icon" aria-hidden="true">
        <AlertIcon />
      </div>
      <div className="error-state__body">
        <h2>{title}</h2>
        <p>{message}</p>
        {requestId ? (
          <p className="error-state__request">
            Request ID: <code>{requestId}</code>
          </p>
        ) : null}
        <div className="error-state__actions">
          {onRetry ? (
            <Button variant="primary" onClick={onRetry}>
              Try again
            </Button>
          ) : null}
          {onBack ? (
            <Button variant="secondary" onClick={onBack}>
              Back to search
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
