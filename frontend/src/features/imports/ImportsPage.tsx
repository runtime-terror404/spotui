import { useCallback } from "react";

import { errorMessage, errorRequestId } from "../../api/errors";
import type { ImportSession } from "../../api/types";
import { ImportsIcon } from "../../components/icons";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SectionHeading } from "../../components/ui/SectionHeading";
import { useUIStore } from "../../state/uiStore";
import { ImportCreateForm } from "./ImportCreateForm";
import { ImportSessionView } from "./ImportSessionView";
import { importStatusLabel, isActiveImportStatus } from "./format";
import { useImportDetail, useImportEvents, useImports } from "./hooks";

function SessionTab({
  session,
  selected,
  onSelect,
}: {
  session: ImportSession;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`import-session-tab ${selected ? "is-selected" : ""}`.trim()}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <span className="import-session-tab__title" title={session.title}>
        {session.title || "Untitled Spotify import"}
      </span>
      <span className="import-session-tab__meta">
        {importStatusLabel(session.status)} · {session.counts.matched}/
        {session.counts.total} matched
      </span>
      {session.counts.queued > 0 ? (
        <span className="import-session-tab__queued">
          {session.counts.queued} queued
        </span>
      ) : null}
    </button>
  );
}

export function ImportsPage() {
  const importsQuery = useImports();
  const selectedImportId = useUIStore((state) => state.selectedImportId);
  const openImports = useUIStore((state) => state.openImports);
  const imports = importsQuery.data?.imports ?? [];
  const activeSession = imports.find((session) =>
    isActiveImportStatus(session.status),
  );
  const selectedSession =
    imports.find((session) => session.id === selectedImportId) ??
    activeSession ??
    imports[0];
  const selectedId = selectedSession?.id ?? null;
  const detail = useImportDetail(selectedId);
  const onDeleted = useCallback(() => openImports(null), [openImports]);
  useImportEvents(selectedId, onDeleted);

  return (
    <div className="imports-page">
      <header className="imports-page__header">
        <p className="eyebrow">Spotify to Amazon</p>
        <h1>Imports</h1>
        <p>
          Import a public Spotify album or playlist, review each source
          occurrence, and choose exact Amazon tracks. Matching never selects a
          candidate for you.
        </p>
      </header>

      <ImportCreateForm
        onCreated={(sessionId) => openImports(sessionId)}
        hasActiveImport={Boolean(activeSession)}
      />

      {importsQuery.isPending ? (
        <div className="imports-page__loading" aria-busy="true">
          <span className="visually-hidden">Loading imports…</span>
          <div className="skeleton skeleton--heading" aria-hidden="true" />
          <div className="skeleton skeleton--row" aria-hidden="true" />
        </div>
      ) : null}

      {importsQuery.isError ? (
        <ErrorState
          title="Could not load Spotify imports"
          message={errorMessage(importsQuery.error)}
          requestId={errorRequestId(importsQuery.error)}
          onRetry={() => {
            void importsQuery.refetch();
          }}
        />
      ) : null}

      {!importsQuery.isPending &&
      !importsQuery.isError &&
      imports.length === 0 ? (
        <EmptyState
          icon={<ImportsIcon />}
          title="No Spotify imports yet"
          description="Paste a public Spotify album or playlist link above to build a reviewable Amazon candidate list."
        />
      ) : null}

      {imports.length > 0 ? (
        <section className="imports-page__sessions" aria-label="Import history">
          <SectionHeading title="Sessions" count={imports.length} />
          <div className="import-session-tabs">
            {imports.map((session) => (
              <SessionTab
                key={session.id}
                session={session}
                selected={session.id === selectedId}
                onSelect={() => openImports(session.id)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {selectedId && detail.isPending ? (
        <div className="imports-page__loading" aria-busy="true">
          <span className="visually-hidden">Loading import details…</span>
          <div className="skeleton skeleton--hero" aria-hidden="true" />
          <div className="skeleton skeleton--heading" aria-hidden="true" />
          <div className="skeleton skeleton--row" aria-hidden="true" />
        </div>
      ) : null}

      {selectedId && detail.isError ? (
        <ErrorState
          title="Could not load this import"
          message={errorMessage(detail.error)}
          requestId={errorRequestId(detail.error)}
          onRetry={() => {
            void detail.refetch();
          }}
        />
      ) : null}

      {detail.data ? (
        <ImportSessionView
          key={detail.data.id}
          detail={detail.data}
          onRemoved={onDeleted}
        />
      ) : null}
    </div>
  );
}
