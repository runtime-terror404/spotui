import { useState } from "react";

import { errorMessage, errorRequestId } from "../../api/errors";
import type { ImportSessionDetail } from "../../api/types";
import { DownloadIcon } from "../../components/icons";
import { Artwork } from "../../components/ui/Artwork";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { SectionHeading } from "../../components/ui/SectionHeading";
import { useSnackbarStore } from "../../state/snackbarStore";
import {
  useCancelImport,
  useDeleteImport,
  useEnqueueImportSelected,
  usePauseImport,
  useResumeImport,
} from "./hooks";
import { ImportSourceRow } from "./ImportSourceRow";
import { importProgressText, importStatusLabel } from "./format";

type ConfirmAction = "cancel" | "delete";

function CountCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="import-count">
      <span className="import-count__value">{value}</span>
      <span className="import-count__label">{label}</span>
    </div>
  );
}

function statusTone(detail: ImportSessionDetail) {
  if (detail.status === "paused") {
    return "warning";
  }
  if (detail.status === "matching_complete") {
    return "success";
  }
  return "neutral";
}

export function ImportSessionView({
  detail,
  onRemoved,
}: {
  detail: ImportSessionDetail;
  onRemoved: () => void;
}) {
  const pause = usePauseImport(detail.id);
  const resume = useResumeImport(detail.id);
  const cancel = useCancelImport(detail.id);
  const remove = useDeleteImport(detail.id);
  const enqueue = useEnqueueImportSelected(detail.id);
  const pushSnackbar = useSnackbarStore((state) => state.push);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [forceLibrary, setForceLibrary] = useState(false);
  const counts = detail.counts;
  const selectedSources = detail.sources.filter(
    (source) => source.review_status === "selected",
  );
  const hasQueueableSelection = selectedSources.some(
    (source) =>
      source.queue_outcome === "none" ||
      source.queue_outcome === "skipped_library",
  );
  const hasSelectedLibraryMatch = selectedSources.some(
    (source) =>
      source.library_match !== null &&
      source.queue_outcome !== "queued" &&
      source.queue_outcome !== "duplicate",
  );
  const actionError =
    pause.error ??
    resume.error ??
    cancel.error ??
    remove.error ??
    enqueue.error;
  const actionBusy =
    pause.isPending ||
    resume.isPending ||
    cancel.isPending ||
    remove.isPending ||
    enqueue.isPending;
  const active =
    detail.status === "extracting" ||
    detail.status === "matching" ||
    detail.status === "paused";
  const skippableLibraryCount = counts.library_skipped;

  const runEnqueue = (force: boolean) => {
    enqueue.mutate(force, {
      onSuccess: (result) => {
        const parts: string[] = [];
        if (result.queued) {
          parts.push(`${result.queued} added to queue`);
        }
        if (result.duplicate) {
          parts.push(`${result.duplicate} already queued`);
        }
        if (result.skipped_library) {
          parts.push(`${result.skipped_library} library matches skipped`);
        }
        pushSnackbar(
          parts.join(" · ") || "No selected occurrences were ready to queue.",
          result.queued ? "success" : "info",
        );
      },
    });
  };

  const confirmCopy =
    confirmAction === "cancel"
      ? {
          title: "Cancel this import?",
          message:
            "Unqueued candidates, selections, and review data will be removed. Downloads already in the queue are kept.",
          label: "Cancel import",
        }
      : {
          title: "Delete this completed import?",
          message:
            "The import and its review data will be removed. Queued jobs, downloaded media, and queue history are kept.",
          label: "Delete import",
        };

  return (
    <section className="import-session" aria-labelledby="import-session-title">
      <header className="import-session__hero">
        <Artwork
          src={detail.artwork_url}
          alt=""
          shape="square"
          className="import-session__art"
        />
        <div className="import-session__body">
          <p className="eyebrow">
            Spotify {detail.spotify_type ?? "album or playlist"}
          </p>
          <h2 id="import-session-title" title={detail.title}>
            {detail.title || "Spotify import"}
          </h2>
          <a
            className="import-session__source"
            href={detail.source_url}
            target="_blank"
            rel="noreferrer"
          >
            Open on Spotify
          </a>
          <div className="import-session__status">
            <span className={`status-pill status-pill--${statusTone(detail)}`}>
              {importStatusLabel(detail.status)}
            </span>
            <span>{importProgressText(detail)}</span>
          </div>
        </div>
      </header>

      {detail.status === "extracting" || detail.status === "matching" ? (
        <div className="import-progress" role="status">
          <span>
            {detail.status === "extracting"
              ? "Reading the public Spotify page…"
              : "Matching source tracks to Amazon Music…"}
          </span>
          <span className="indeterminate-bar" aria-hidden="true" />
        </div>
      ) : null}

      <div className="import-counts" aria-label="Import review counts">
        <CountCard label="Matched" value={counts.matched} />
        <CountCard label="Selected" value={counts.selected} />
        <CountCard label="Queued" value={counts.queued} />
        <CountCard label="Needs review" value={counts.unresolved} />
        <CountCard label="Skipped" value={counts.skipped} />
        <CountCard label="Duplicates" value={counts.duplicate} />
      </div>

      {detail.last_error ? (
        <div className="inline-error" role="alert">
          <p>{detail.last_error}</p>
        </div>
      ) : null}
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

      <div className="import-session__actions">
        <div className="import-session__primary-actions">
          <Button
            variant="primary"
            icon={<DownloadIcon />}
            disabled={!hasQueueableSelection || actionBusy}
            onClick={() => runEnqueue(forceLibrary)}
          >
            {enqueue.isPending
              ? "Adding…"
              : hasQueueableSelection
                ? `Add selected to queue (${selectedSources.length})`
                : selectedSources.length > 0
                  ? "Selected tracks are queued"
                  : "Add selected to queue (0)"}
          </Button>
          {hasSelectedLibraryMatch || skippableLibraryCount > 0 ? (
            <label className="import-session__override">
              <input
                type="checkbox"
                checked={forceLibrary}
                onChange={(event) => setForceLibrary(event.target.checked)}
              />
              Queue selected tracks that match my library anyway
            </label>
          ) : null}
        </div>
        <div className="import-session__lifecycle-actions">
          {detail.status === "matching" ? (
            <Button
              variant="secondary"
              disabled={actionBusy}
              onClick={() => pause.mutate()}
            >
              Pause matching
            </Button>
          ) : null}
          {detail.status === "paused" ? (
            <Button
              variant="secondary"
              disabled={actionBusy}
              onClick={() => resume.mutate()}
            >
              Resume matching
            </Button>
          ) : null}
          {active ? (
            <Button
              variant="ghost"
              className="button--danger-text"
              disabled={actionBusy}
              onClick={() => setConfirmAction("cancel")}
            >
              Cancel import
            </Button>
          ) : null}
          {detail.status === "matching_complete" ? (
            <Button
              variant="ghost"
              className="button--danger-text"
              disabled={actionBusy}
              onClick={() => setConfirmAction("delete")}
            >
              Delete import
            </Button>
          ) : null}
        </div>
      </div>

      {skippableLibraryCount > 0 ? (
        <div className="import-library-notice">
          <p>
            {skippableLibraryCount} selected occurrence
            {skippableLibraryCount === 1 ? " was" : "s were"} skipped because
            the Amazon track appears to be in your library.
          </p>
          <Button
            variant="secondary"
            disabled={actionBusy}
            onClick={() => runEnqueue(true)}
          >
            Queue library matches anyway
          </Button>
        </div>
      ) : null}

      <section className="import-sources" aria-label="Source track review">
        <SectionHeading title="Source tracks" count={detail.sources.length} />
        {detail.sources.length === 0 ? (
          <p className="import-sources__empty">
            No tracks were extracted from this Spotify item.
          </p>
        ) : (
          <div className="import-source-list">
            {detail.sources.map((source, index) => (
              <ImportSourceRow
                key={source.id}
                sessionId={detail.id}
                source={source}
                displayPosition={index + 1}
              />
            ))}
          </div>
        )}
      </section>

      <ConfirmDialog
        open={confirmAction !== null}
        title={confirmAction ? confirmCopy.title : ""}
        message={confirmAction ? confirmCopy.message : ""}
        confirmLabel={confirmAction ? confirmCopy.label : ""}
        destructive
        busy={cancel.isPending || remove.isPending}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => {
          if (confirmAction === "cancel") {
            cancel.mutate(undefined, {
              onSuccess: () => {
                setConfirmAction(null);
                onRemoved();
                pushSnackbar("Spotify import cancelled.", "info");
              },
              onError: () => setConfirmAction(null),
            });
          } else if (confirmAction === "delete") {
            remove.mutate(undefined, {
              onSuccess: () => {
                setConfirmAction(null);
                onRemoved();
                pushSnackbar("Completed import deleted.", "info");
              },
              onError: () => setConfirmAction(null),
            });
          }
        }}
      />
    </section>
  );
}
