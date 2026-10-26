import { useId, useState } from "react";

import { errorMessage, errorRequestId } from "../../api/errors";
import { Button } from "../../components/ui/Button";
import { useSnackbarStore } from "../../state/snackbarStore";
import { useCreateImport } from "./hooks";

export function ImportCreateForm({
  onCreated,
  hasActiveImport,
}: {
  onCreated: (sessionId: string) => void;
  hasActiveImport: boolean;
}) {
  const [url, setUrl] = useState("");
  const create = useCreateImport();
  const pushSnackbar = useSnackbarStore((state) => state.push);
  const inputId = useId();
  const hintId = useId();

  return (
    <form
      className="import-create"
      onSubmit={(event) => {
        event.preventDefault();
        const value = url.trim();
        if (!value) {
          return;
        }
        create.mutate(value, {
          onSuccess: (detail) => {
            setUrl("");
            onCreated(detail.id);
            pushSnackbar("Spotify import started.", "success");
          },
        });
      }}
    >
      <div className="import-create__heading">
        <label htmlFor={inputId}>Import a public Spotify album or playlist</label>
        <span id={hintId}>
          Paste an open.spotify.com or spotify.link URL. No Spotify login is used.
        </span>
      </div>
      <div className="import-create__controls">
        <input
          id={inputId}
          type="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://open.spotify.com/playlist/…"
          aria-describedby={hintId}
          autoComplete="off"
          spellCheck={false}
          disabled={create.isPending}
        />
        <Button
          type="submit"
          variant="primary"
          disabled={!url.trim() || create.isPending}
        >
          {create.isPending ? "Reading Spotify…" : "Import"}
        </Button>
      </div>
      {hasActiveImport ? (
        <p className="import-create__note">
          One import can match at a time. Pause or cancel the active import before
          starting another.
        </p>
      ) : null}
      {create.isError ? (
        <div className="inline-error" role="alert">
          <p>{errorMessage(create.error)}</p>
          {errorRequestId(create.error) ? (
            <p className="inline-error__request">
              Request ID: <code>{errorRequestId(create.error)}</code>
            </p>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
