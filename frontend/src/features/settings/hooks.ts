import { useQuery } from "@tanstack/react-query";

import { fetchLibrary, fetchSystemInfo } from "../../api/client";

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system-info"],
    queryFn: ({ signal }) => fetchSystemInfo(signal),
    staleTime: 60_000,
    retry: false,
  });
}

export function useLibraryOverview() {
  return useQuery({
    queryKey: ["library-overview"],
    queryFn: ({ signal }) => fetchLibrary(signal),
    staleTime: 60_000,
    retry: false,
  });
}
