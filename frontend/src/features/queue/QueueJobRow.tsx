import type { QueueJob } from "../../api/types";
import { AlertIcon, CheckIcon, ClockIcon, DownloadIcon } from "../../components/icons";
import { Button } from "../../components/ui/Button";
import {
  fileName,
  formatRelative,
  isActiveState,
  jobDetail,
  jobStatusLabel,
  jobTone,
} from "./format";

function StatusIcon({ state }: { state: QueueJob["state"] }) {
  switch (state) {
    case "completed":
      return <CheckIcon />;
    case "failed":
      return <AlertIcon />;
    case "starting":
    case "running":
    case "cancelling":
      return <DownloadIcon />;
    default:
      return <ClockIcon />;
  }
}

interface QueueJobRowProps {
  job: QueueJob;
  compact?: boolean;
  busy?: boolean;
  onCancel?: (job: QueueJob) => void;
  onRetry?: (job: QueueJob) => void;
}

export function QueueJobRow({
  job,
  compact = false,
  busy = false,
  onCancel,
  onRetry,
}: QueueJobRowProps) {
  const label = jobStatusLabel(job);
  const tone = jobTone(job.state);
  const detail = jobDetail(job);
  const active = isActiveState(job.state);
  const canCancel = job.state === "queued" || active;
  const canRetry = job.state === "failed" || job.state === "interrupted";

  return (
    <article
      className={`queue-job queue-job--${tone} ${compact ? "queue-job--compact" : ""}`.trim()}
      aria-label={`${job.title}, ${label}`}
    >
      <div className="queue-job__icon" aria-hidden="true">
        <StatusIcon state={job.state} />
      </div>
      <div className="queue-job__body">
        <div className="queue-job__heading">
          <span className="queue-job__title" title={job.title}>
            {job.title}
          </span>
          <span className="queue-job__time">{formatRelative(job.updated_at)}</span>
        </div>
        {job.artist ? (
          <span className="queue-job__artist" title={job.artist}>
            {job.artist}
          </span>
        ) : null}
        <span className={`queue-job__state queue-job__state--${tone}`}>
          {label}
        </span>
        {active ? (
          <span className="queue-job__progress" aria-hidden="true">
            <span />
          </span>
        ) : null}
        {detail ? (
          <span
            className="queue-job__detail"
            title={detail}
          >
            {job.state === "completed" ? fileName(job.output_path) : detail}
          </span>
        ) : null}
        {job.attempt_count > 1 ? (
          <span className="queue-job__attempt">
            Attempt {job.attempt_count}
          </span>
        ) : null}
      </div>
      <div className="queue-job__actions">
        {canCancel && onCancel ? (
          <Button
            variant="ghost"
            className="button--small"
            disabled={busy || job.state === "cancelling"}
            onClick={() => onCancel(job)}
            aria-label={`Cancel download ${job.title}`}
          >
            {job.state === "cancelling" ? "Cancelling…" : "Cancel"}
          </Button>
        ) : null}
        {canRetry && onRetry ? (
          <Button
            variant="secondary"
            className="button--small"
            disabled={busy}
            onClick={() => onRetry(job)}
            aria-label={`Retry download ${job.title}`}
          >
            Retry
          </Button>
        ) : null}
      </div>
    </article>
  );
}
