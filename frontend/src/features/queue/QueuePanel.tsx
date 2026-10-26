import { useEffect, useState } from "react";

import { errorMessage } from "../../api/errors";
import { QueueIcon } from "../../components/icons";
import { Button } from "../../components/ui/Button";
import { useUIStore } from "../../state/uiStore";
import { QueueJobRow } from "./QueueJobRow";
import {
  COMPACT_COMPLETED_HOLD_SECONDS,
  compactQueueJobs,
} from "./format";
import { useCancelJob, useDismissJob, useQueue, useRetryJob } from "./hooks";

export function QueuePanel() {
  const queue = useQueue();
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const dismiss = useDismissJob();
  const openQueue = useUIStore((state) => state.openQueue);
  const counts = queue.data?.counts;
  const allJobs = queue.data?.jobs ?? [];
  const [holdClock, setHoldClock] = useState(() => Date.now());
  const holdCutoff = holdClock / 1000 - COMPACT_COMPLETED_HOLD_SECONDS;
  const hasRecentCompleted = allJobs.some(
    (job) =>
      job.state === "completed" && (job.completed_at ?? job.updated_at) > holdCutoff,
  );
  useEffect(() => {
    if (!hasRecentCompleted) {
      return;
    }
    const timer = window.setInterval(() => setHoldClock(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [hasRecentCompleted]);
  const jobs = compactQueueJobs(allJobs, holdClock / 1000).slice(0, 6);
  const busy = cancel.isPending || retry.isPending || dismiss.isPending;

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
          <p>No active downloads.</p>
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
              onDismiss={(item) => dismiss.mutate(item)}
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
