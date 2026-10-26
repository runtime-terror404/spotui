import type {
  BatchEnqueueResponse,
  EntityDetail,
  EnqueueInput,
  EnqueueResponse,
  NowPlayingResponse,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
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
