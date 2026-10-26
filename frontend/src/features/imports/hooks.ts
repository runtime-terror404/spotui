import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelImport,
  createSpotifyImport,
  deleteImport,
  enqueueImportSelected,
  fetchImport,
  fetchImports,
  pauseImport,
  resumeImport,
  searchImportSource,
  selectImportCandidate,
  skipImportSource,
} from "../../api/client";
import type { ImportListResponse } from "../../api/types";

const importsKey = ["imports"] as const;
const importKey = (sessionId: string) => ["import", sessionId] as const;

export function useImports() {
  return useQuery({
    queryKey: importsKey,
    queryFn: ({ signal }) => fetchImports(signal),
    staleTime: 5_000,
    retry: false,
  });
}

export function useImportDetail(sessionId: string | null) {
  return useQuery({
    queryKey: ["import", sessionId],
    queryFn: ({ signal }) => fetchImport(sessionId!, signal),
    enabled: sessionId !== null,
    retry: false,
  });
}

export function useImportEvents(
  sessionId: string | null,
  onDeleted?: () => void,
) {
  const queryClient = useQueryClient();
  const onDeletedRef = useRef(onDeleted);
  useEffect(() => {
    onDeletedRef.current = onDeleted;
  }, [onDeleted]);

  useEffect(() => {
    if (!sessionId || typeof EventSource === "undefined") {
      return;
    }
    const source = new EventSource(
      `/api/v1/imports/${encodeURIComponent(sessionId)}/events`,
    );
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: importKey(sessionId) });
      void queryClient.invalidateQueries({ queryKey: importsKey });
    };
    const deleted = () => {
      void queryClient.invalidateQueries({ queryKey: importsKey });
      source.close();
      onDeletedRef.current?.();
    };
    source.addEventListener("import", refresh);
    source.addEventListener("deleted", deleted);
    return () => source.close();
  }, [queryClient, sessionId]);
}

function invalidateSession(
  queryClient: ReturnType<typeof useQueryClient>,
  sessionId: string,
) {
  void queryClient.invalidateQueries({ queryKey: importKey(sessionId) });
  void queryClient.invalidateQueries({ queryKey: importsKey });
}

export function useCreateImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createSpotifyImport,
    onSuccess: (detail) => {
      queryClient.setQueryData(importKey(detail.id), detail);
      queryClient.setQueryData<ImportListResponse>(importsKey, (current) => ({
        imports: [
          detail,
          ...(current?.imports.filter((item) => item.id !== detail.id) ?? []),
        ],
      }));
      void queryClient.invalidateQueries({ queryKey: importsKey });
    },
  });
}

export function usePauseImport(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => pauseImport(sessionId),
    onSuccess: (detail) => {
      queryClient.setQueryData(importKey(sessionId), detail);
      invalidateSession(queryClient, sessionId);
    },
  });
}

export function useResumeImport(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => resumeImport(sessionId),
    onSuccess: (detail) => {
      queryClient.setQueryData(importKey(sessionId), detail);
      invalidateSession(queryClient, sessionId);
    },
  });
}

export function useCancelImport(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelImport(sessionId),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: importKey(sessionId) });
      void queryClient.invalidateQueries({ queryKey: importsKey });
    },
  });
}

export function useDeleteImport(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteImport(sessionId),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: importKey(sessionId) });
      void queryClient.invalidateQueries({ queryKey: importsKey });
    },
  });
}

export function useSelectImportCandidate(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceId,
      candidateId,
    }: {
      sourceId: string;
      candidateId: string;
    }) => selectImportCandidate(sessionId, sourceId, candidateId),
    onSuccess: (detail) => {
      queryClient.setQueryData(importKey(sessionId), detail);
      invalidateSession(queryClient, sessionId);
    },
  });
}

export function useSkipImportSource(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => skipImportSource(sessionId, sourceId),
    onSuccess: (detail) => {
      queryClient.setQueryData(importKey(sessionId), detail);
      invalidateSession(queryClient, sessionId);
    },
  });
}

export function useSearchImportSource(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => searchImportSource(sessionId, sourceId),
    onSuccess: (detail) => {
      queryClient.setQueryData(importKey(sessionId), detail);
      invalidateSession(queryClient, sessionId);
    },
  });
}

export function useEnqueueImportSelected(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (forceLibrary: boolean) =>
      enqueueImportSelected(sessionId, forceLibrary),
    onSuccess: (result) => {
      queryClient.setQueryData(importKey(sessionId), result.session);
      invalidateSession(queryClient, sessionId);
      void queryClient.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}
