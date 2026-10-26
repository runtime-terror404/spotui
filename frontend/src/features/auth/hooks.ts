import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchAuthStatus,
  fetchPairedDevices,
  fetchPairingInfo,
  pairBrowser,
  revokePairedDevice,
} from "../../api/client";

export const authStatusKey = ["auth-status"] as const;

export function useAuthStatus() {
  return useQuery({
    queryKey: authStatusKey,
    queryFn: ({ signal }) => fetchAuthStatus(signal),
    staleTime: 30_000,
    retry: false,
  });
}

export function usePairBrowser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ code, label }: { code: string; label?: string }) =>
      pairBrowser(code, label),
    onSuccess: (status) => {
      queryClient.setQueryData(authStatusKey, status);
      void queryClient.invalidateQueries();
    },
  });
}

export function usePairingInfo(enabled: boolean) {
  return useQuery({
    queryKey: ["pairing-info"],
    queryFn: ({ signal }) => fetchPairingInfo(signal),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

export function usePairedDevices(enabled: boolean) {
  return useQuery({
    queryKey: ["paired-devices"],
    queryFn: ({ signal }) => fetchPairedDevices(signal),
    enabled,
    staleTime: 10_000,
    retry: false,
  });
}

export function useRevokeDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revokePairedDevice,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["paired-devices"] });
    },
  });
}
