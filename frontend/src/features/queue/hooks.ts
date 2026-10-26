import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelQueueJob,
  dismissQueueJob,
  enqueueBatch,
  enqueueTrack,
  fetchQueue,
  retryQueueJob,
} from "../../api/client";
import { errorMessage } from "../../api/errors";
import type { EnqueueInput, QueueJob, QueueSnapshot } from "../../api/types";
import { useSnackbarStore } from "../../state/snackbarStore";

export const queueQueryKey = ["queue"] as const;
const ACTIVE_QUEUE_POLL_MS = 1_500;
const IDLE_QUEUE_POLL_MS = 10_000;

interface DismissMutationContext {
  previous: QueueSnapshot | undefined;
}

function removeJobFromSnapshot(
  snapshot: QueueSnapshot,
  job: QueueJob,
): QueueSnapshot {
  const counts = { ...snapshot.counts };
  switch (job.state) {
    case "queued":
      counts.queued = Math.max(0, counts.queued - 1);
      break;
    case "failed":
      counts.failed = Math.max(0, counts.failed - 1);
      break;
    case "interrupted":
      counts.interrupted = Math.max(0, counts.interrupted - 1);
      break;
    case "cancelled":
      counts.cancelled = Math.max(0, counts.cancelled - 1);
      break;
    default:
      break;
  }
  return {
    ...snapshot,
    counts,
    jobs: snapshot.jobs.filter((item) => item.id !== job.id),
  };
}

export function useQueue() {
  return useQuery({
    queryKey: queueQueryKey,
    queryFn: ({ signal }) => fetchQueue(signal),
    refetchInterval: (query) => {
      const counts = query.state.data?.counts;
      return counts && counts.active === 0 && counts.queued === 0
        ? IDLE_QUEUE_POLL_MS
        : ACTIVE_QUEUE_POLL_MS;
    },
    staleTime: 0,
    retry: false,
  });
}

function notify(message: string, tone: "info" | "success" | "error") {
  useSnackbarStore.getState().push(message, tone);
}

export function useEnqueueTrack() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EnqueueInput) => enqueueTrack(input),
    onSuccess: (response) => {
      notify(
        response.duplicate
          ? `Already queued: ${response.job.title}`
          : `Added to queue: ${response.job.title}`,
        response.duplicate ? "info" : "success",
      );
      void queryClient.invalidateQueries({ queryKey: queueQueryKey });
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
}

export function useEnqueueBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (items: EnqueueInput[]) => enqueueBatch(items),
    onSuccess: (result) => {
      const parts = [];
      if (result.added) {
        parts.push(`${result.added} added`);
      }
      if (result.duplicates) {
        parts.push(`${result.duplicates} already queued`);
      }
      if (result.skipped_library) {
        parts.push(`${result.skipped_library} already in library`);
      }
      if (result.invalid) {
        parts.push(`${result.invalid} invalid`);
      }
      notify(parts.length ? parts.join(" · ") : "Nothing new to queue.", "success");
      void queryClient.invalidateQueries({ queryKey: queueQueryKey });
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => cancelQueueJob(jobId),
    onSuccess: (job) => {
      notify(
        job.state === "cancelled" ? `Cancelled: ${job.title}` : `Cancelling: ${job.title}`,
        "info",
      );
      void queryClient.invalidateQueries({ queryKey: queueQueryKey });
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
}

export function useRetryJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => retryQueueJob(jobId),
    onSuccess: (job) => {
      notify(`Queued again: ${job.title}`, "success");
      void queryClient.invalidateQueries({ queryKey: queueQueryKey });
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
}

export function useDismissJob() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, QueueJob, DismissMutationContext>({
    mutationFn: (job) => dismissQueueJob(job.id),
    onMutate: async (job) => {
      await queryClient.cancelQueries({ queryKey: queueQueryKey });
      const previous = queryClient.getQueryData<QueueSnapshot>(queueQueryKey);
      if (previous) {
        queryClient.setQueryData(queueQueryKey, removeJobFromSnapshot(previous, job));
      }
      return { previous };
    },
    onError: (error, _job, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queueQueryKey, context.previous);
      }
      notify(errorMessage(error), "error");
    },
    onSuccess: (_result, job) => notify(`Removed: ${job.title}`, "info"),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queueQueryKey });
    },
  });
}
