import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelQueueJob,
  enqueueBatch,
  enqueueTrack,
  fetchQueue,
  retryQueueJob,
} from "../../api/client";
import { errorMessage } from "../../api/errors";
import type { EnqueueInput } from "../../api/types";
import { useSnackbarStore } from "../../state/snackbarStore";

export const queueQueryKey = ["queue"] as const;

export function useQueue() {
  return useQuery({
    queryKey: queueQueryKey,
    queryFn: ({ signal }) => fetchQueue(signal),
    refetchInterval: 1500,
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
