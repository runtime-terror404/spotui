import type { JobState, QueueJob } from "../../api/types";

export function jobStatusLabel(job: QueueJob): string {
  switch (job.state) {
    case "queued":
      return "Waiting";
    case "starting":
    case "running":
      return job.status_message || "Downloading";
    case "cancelling":
      return "Cancelling";
    case "completed":
      return job.status_message === "already in library"
        ? "Already in library"
        : "Completed";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
    case "interrupted":
      return "Interrupted";
  }
}

export function jobDetail(job: QueueJob): string | undefined {
  if (job.state === "failed" || job.state === "interrupted") {
    return job.last_error || job.status_message;
  }
  if (job.state === "completed" && job.output_path) {
    return job.output_path;
  }
  return undefined;
}

export function jobTone(
  state: JobState,
): "active" | "success" | "error" | "warning" | "neutral" {
  switch (state) {
    case "starting":
    case "running":
    case "cancelling":
      return "active";
    case "completed":
      return "success";
    case "failed":
      return "error";
    case "interrupted":
      return "warning";
    default:
      return "neutral";
  }
}

export function isActiveState(state: JobState): boolean {
  return state === "starting" || state === "running" || state === "cancelling";
}

export function formatRelative(timestamp: number): string {
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
  if (seconds < 10) {
    return "just now";
  }
  if (seconds < 60) {
    return `${seconds}s ago`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  return `${Math.floor(hours / 24)}d ago`;
}

export function fileName(path: string | undefined): string | undefined {
  if (!path) {
    return undefined;
  }
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}
