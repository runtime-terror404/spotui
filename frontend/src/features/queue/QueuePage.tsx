import { errorMessage } from "../../api/errors";
import type { QueueJob } from "../../api/types";
import { QueueIcon } from "../../components/icons";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SectionHeading } from "../../components/ui/SectionHeading";
import { useUIStore } from "../../state/uiStore";
import { QueueJobRow } from "./QueueJobRow";
import { useCancelJob, useQueue, useRetryJob } from "./hooks";
import { isActiveState } from "./format";

function QueueSection({
  title,
  jobs,
  busy,
  onCancel,
  onRetry,
}: {
  title: string;
  jobs: QueueJob[];
  busy: boolean;
  onCancel: (job: QueueJob) => void;
  onRetry: (job: QueueJob) => void;
}) {
  if (jobs.length === 0) {
    return null;
  }
  return (
    <section className="queue-section" aria-label={title}>
      <SectionHeading title={title} count={jobs.length} />
      <div className="queue-section__list">
        {jobs.map((job) => (
          <QueueJobRow
            key={job.id}
            job={job}
            busy={busy}
            onCancel={onCancel}
            onRetry={onRetry}
          />
        ))}
      </div>
    </section>
  );
}

function CountCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="queue-count">
      <span className="queue-count__value">{value}</span>
      <span className="queue-count__label">{label}</span>
    </div>
  );
}

export function QueuePage() {
  const queue = useQueue();
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const openSearch = useUIStore((state) => state.openSearch);
  const busy = cancel.isPending || retry.isPending;
  const onCancel = (job: QueueJob) => cancel.mutate(job.id);
  const onRetry = (job: QueueJob) => retry.mutate(job.id);

  if (queue.isPending) {
    return (
      <div className="queue-page" aria-busy="true">
        <span className="visually-hidden">Loading queue…</span>
        <div className="skeleton skeleton--heading" aria-hidden="true" />
        <div className="skeleton skeleton--row" aria-hidden="true" />
        <div className="skeleton skeleton--row" aria-hidden="true" />
      </div>
    );
  }

  if (queue.isError) {
    return (
      <ErrorState
        title="Could not load the queue"
        message={errorMessage(queue.error)}
        onRetry={() => {
          void queue.refetch();
        }}
      />
    );
  }

  const { jobs, counts } = queue.data;
  const active = jobs.filter((job) => isActiveState(job.state));
  const waiting = jobs.filter((job) => job.state === "queued");
  const attention = jobs.filter(
    (job) => job.state === "failed" || job.state === "interrupted",
  );
  const history = jobs.filter(
    (job) => job.state === "completed" || job.state === "cancelled",
  );

  return (
    <div className="queue-page">
      <header className="queue-page__header">
        <div>
          <p className="eyebrow">Downloads</p>
          <h1>Queue</h1>
          <p className="queue-page__summary" role="status" aria-live="polite">
            One download at a time · updates every few seconds
          </p>
        </div>
        <div className="queue-page__counts" aria-label="Queue counts">
          <CountCard label="Active" value={counts.active} />
          <CountCard label="Waiting" value={counts.queued} />
          <CountCard label="Failed" value={counts.failed} />
          <CountCard label="Completed" value={counts.completed} />
        </div>
      </header>

      {jobs.length === 0 ? (
        <EmptyState
          icon={<QueueIcon />}
          title="No downloads yet"
          description="Find a track, album, artist, or playlist and add it to the queue."
          action={
            <Button variant="primary" onClick={openSearch}>
              Search music
            </Button>
          }
        />
      ) : (
        <>
          <QueueSection
            title="Active"
            jobs={active}
            busy={busy}
            onCancel={onCancel}
            onRetry={onRetry}
          />
          <QueueSection
            title="Waiting"
            jobs={waiting}
            busy={busy}
            onCancel={onCancel}
            onRetry={onRetry}
          />
          <QueueSection
            title="Needs attention"
            jobs={attention}
            busy={busy}
            onCancel={onCancel}
            onRetry={onRetry}
          />
          <QueueSection
            title="History"
            jobs={history}
            busy={busy}
            onCancel={onCancel}
            onRetry={onRetry}
          />
        </>
      )}
    </div>
  );
}
