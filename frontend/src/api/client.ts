import type {
  AuthStatus,
  BatchEnqueueResponse,
  EntityDetail,
  EnqueueInput,
  EnqueueResponse,
  ImportEnqueueResponse,
  ImportListResponse,
  ImportSessionDetail,
  NowPlayingResponse,
  PairedDeviceList,
  PairingInfo,
  ProblemDetails,
  ProblemIssue,
  QueueJob,
  QueueSnapshot,
  SearchResponse,
} from "./types";

export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly issues: ProblemIssue[];

  constructor(problem: ProblemDetails | null, status: number) {
    super(problem?.detail ?? `Request failed with status ${status}.`);
    this.name = "ApiProblem";
    this.status = problem?.status ?? status;
    this.code = problem?.code ?? "http_error";
    this.requestId = problem?.request_id ?? "";
    this.issues = problem?.errors ?? [];
  }
}

export class NetworkProblem extends Error {
  constructor() {
    super("Could not reach SpotUI. Check that the local server is running.");
    this.name = "NetworkProblem";
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  for (const item of document.cookie.split(";")) {
    const value = item.trim();
    if (value.startsWith(prefix)) {
      return decodeURIComponent(value.slice(prefix.length));
    }
  }
  return undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (!SAFE_METHODS.has(method) && !headers.has("X-CSRF-Token")) {
    const csrfToken = readCookie("spotui_csrf");
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
    });
  } catch {
    throw new NetworkProblem();
  }

  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/problem+json")) {
      try {
        problem = (await response.json()) as ProblemDetails;
      } catch {
        problem = null;
      }
    }
    throw new ApiProblem(problem, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("SpotUI returned an unexpected response.");
  }
}

export function searchAmazon(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query });
  return request<SearchResponse>(`/api/v1/search?${params.toString()}`, {
    signal,
  });
}

export function fetchEntityDetail(
  url: string,
  signal?: AbortSignal,
): Promise<EntityDetail> {
  const params = new URLSearchParams({ url });
  return request<EntityDetail>(
    `/api/v1/entities/detail?${params.toString()}`,
    { signal },
  );
}

export function fetchQueue(signal?: AbortSignal): Promise<QueueSnapshot> {
  return request<QueueSnapshot>("/api/v1/queue", { signal });
}

export function fetchNowPlaying(
  signal?: AbortSignal,
): Promise<NowPlayingResponse> {
  return request<NowPlayingResponse>("/api/v1/now-playing", { signal });
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function enqueueTrack(input: EnqueueInput): Promise<EnqueueResponse> {
  return postJson<EnqueueResponse>("/api/v1/queue/jobs", input);
}

export function enqueueBatch(
  items: EnqueueInput[],
): Promise<BatchEnqueueResponse> {
  return postJson<BatchEnqueueResponse>("/api/v1/queue/batch", { items });
}

export function cancelQueueJob(jobId: string): Promise<QueueJob> {
  return postJson<QueueJob>(`/api/v1/queue/jobs/${encodeURIComponent(jobId)}/cancel`);
}

export function retryQueueJob(jobId: string): Promise<QueueJob> {
  return postJson<QueueJob>(`/api/v1/queue/jobs/${encodeURIComponent(jobId)}/retry`);
}

export function fetchImports(signal?: AbortSignal): Promise<ImportListResponse> {
  return request<ImportListResponse>("/api/v1/imports", { signal });
}

export function fetchImport(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ImportSessionDetail> {
  return request<ImportSessionDetail>(
    `/api/v1/imports/${encodeURIComponent(sessionId)}`,
    { signal },
  );
}

export function createSpotifyImport(
  url: string,
): Promise<ImportSessionDetail> {
  return postJson<ImportSessionDetail>("/api/v1/imports", { url });
}

function importAction(
  sessionId: string,
  action: "pause" | "resume",
): Promise<ImportSessionDetail> {
  return postJson<ImportSessionDetail>(
    `/api/v1/imports/${encodeURIComponent(sessionId)}/${action}`,
  );
}

export function pauseImport(sessionId: string): Promise<ImportSessionDetail> {
  return importAction(sessionId, "pause");
}

export function resumeImport(sessionId: string): Promise<ImportSessionDetail> {
  return importAction(sessionId, "resume");
}

export function cancelImport(sessionId: string): Promise<void> {
  return postJson<void>(`/api/v1/imports/${encodeURIComponent(sessionId)}/cancel`);
}

export function deleteImport(sessionId: string): Promise<void> {
  return request<void>(`/api/v1/imports/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function selectImportCandidate(
  sessionId: string,
  sourceId: string,
  candidateId: string,
): Promise<ImportSessionDetail> {
  return postJson<ImportSessionDetail>(
    `/api/v1/imports/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(sourceId)}/select`,
    { candidate_id: candidateId },
  );
}

export function skipImportSource(
  sessionId: string,
  sourceId: string,
): Promise<ImportSessionDetail> {
  return postJson<ImportSessionDetail>(
    `/api/v1/imports/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(sourceId)}/skip`,
  );
}

export function searchImportSource(
  sessionId: string,
  sourceId: string,
): Promise<ImportSessionDetail> {
  return postJson<ImportSessionDetail>(
    `/api/v1/imports/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(sourceId)}/search`,
  );
}

export function enqueueImportSelected(
  sessionId: string,
  forceLibrary = false,
): Promise<ImportEnqueueResponse> {
  return postJson<ImportEnqueueResponse>(
    `/api/v1/imports/${encodeURIComponent(sessionId)}/enqueue`,
    { force_library: forceLibrary },
  );
}

export function fetchAuthStatus(signal?: AbortSignal): Promise<AuthStatus> {
  return request<AuthStatus>("/api/v1/auth/status", {
    signal,
    cache: "no-store",
  });
}

export function pairBrowser(
  code: string,
  label?: string,
): Promise<AuthStatus> {
  return postJson<AuthStatus>("/api/v1/auth/pair", { code, label });
}

export function fetchPairingInfo(signal?: AbortSignal): Promise<PairingInfo> {
  return request<PairingInfo>("/api/v1/devices/pairing", {
    signal,
    cache: "no-store",
  });
}

export function fetchPairedDevices(
  signal?: AbortSignal,
): Promise<PairedDeviceList> {
  return request<PairedDeviceList>("/api/v1/devices", {
    signal,
    cache: "no-store",
  });
}

export function revokePairedDevice(deviceId: string): Promise<void> {
  return request<void>(
    `/api/v1/devices/${encodeURIComponent(deviceId)}`,
    { method: "DELETE" },
  );
}
