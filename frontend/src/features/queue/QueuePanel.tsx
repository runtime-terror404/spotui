import { errorMessage } from "../../api/errors";
import { QueueIcon } from "../../components/icons";
import { Button } from "../../components/ui/Button";
import { useUIStore } from "../../state/uiStore";
import { QueueJobRow } from "./QueueJobRow";
import { useCancelJob, useQueue, useRetryJob } from "./hooks";

export function QueuePanel() {
  const queue = useQueue();
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const openQueue = useUIStore((state) => state.openQueue);
  const counts = queue.data?.counts;
  const jobs = queue.data?.jobs.slice(0, 6) ?? [];
  const busy = cancel.isPending || retry.isPending;

  return (
    <aside className="queue-panel" aria-label="Download queue">
      <div className="queue-panel__header">
        <div>
          <h2>Queue</h2>
          <p className="queue-panel__counts" role="status" aria-live="polite">
            {counts ? `${counts.active} active · ${counts.queued} waiting` : "Loading…"}
          </p>
        </div>
        <Button variant="ghost" className="button--small" onClick={openQueue}>
          Open queue
        </Button>
      </div>

      {queue.isError ? (
        <div className="queue-panel__error">
          <p>{errorMessage(queue.error)}</p>
          <Button
            variant="secondary"
            className="button--small"
            onClick={() => {
              void queue.refetch();
            }}
          >
            Retry
          </Button>
        </div>
      ) : null}

      {!queue.isError && !queue.isPending && jobs.length === 0 ? (
        <div className="queue-panel__empty">
          <QueueIcon />
          <p>No downloads queued.</p>
        </div>
      ) : null}

      {jobs.length > 0 ? (
        <div className="queue-panel__list">
          {jobs.map((job) => (
            <QueueJobRow
              key={job.id}
              job={job}
              compact
              busy={busy}
              onCancel={(item) => cancel.mutate(item.id)}
              onRetry={(item) => retry.mutate(item.id)}
            />
          ))}
        </div>
      ) : null}

      {counts && (counts.failed > 0 || counts.interrupted > 0) ? (
        <p className="queue-panel__alert">
          {counts.failed + counts.interrupted} need attention
        </p>
      ) : null}
    </aside>
  );
}
