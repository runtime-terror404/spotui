import type {
  ImportSession,
  ImportSourceTrack,
  ImportStatus,
  MatchingStatus,
} from "../../api/types";

export function importStatusLabel(status: ImportStatus): string {
  switch (status) {
    case "extracting":
      return "Extracting";
    case "matching":
      return "Matching";
    case "paused":
      return "Paused";
    case "matching_complete":
      return "Review ready";
  }
}

export function matchingStatusLabel(status: MatchingStatus): string {
  switch (status) {
    case "pending":
      return "Waiting";
    case "searching":
      return "Searching";
    case "candidates_ready":
      return "Candidates ready";
    case "no_results":
      return "No results";
    case "failed":
      return "Search failed";
  }
}

export function sourceStatusLabel(source: ImportSourceTrack): string {
  if (source.queue_outcome === "queued") {
    return "Queued";
  }
  if (source.queue_outcome === "duplicate") {
    return "Already queued";
  }
  if (source.queue_outcome === "skipped_library") {
    return "In library";
  }
  if (source.review_status === "skipped") {
    return "Skipped";
  }
  if (source.review_status === "selected") {
    return "Selected";
  }
  return matchingStatusLabel(source.matching_status);
}

export function sourceStatusTone(
  source: ImportSourceTrack,
): "success" | "warning" | "error" | "neutral" {
  if (source.queue_outcome === "queued") {
    return "success";
  }
  if (
    source.queue_outcome === "skipped_library" ||
    source.review_status === "skipped" ||
    source.matching_status === "no_results"
  ) {
    return "warning";
  }
  if (source.matching_status === "failed") {
    return "error";
  }
  return "neutral";
}

export function isActiveImportStatus(status: ImportStatus): boolean {
  return status === "extracting" || status === "matching" || status === "paused";
}

export function importProgressText(session: ImportSession): string {
  if (session.status === "extracting") {
    return "Reading the public Spotify page";
  }
  const searched =
    session.counts.matched +
    session.counts.no_results +
    session.counts.failed;
  return `${searched} of ${session.counts.total} searched`;
}
