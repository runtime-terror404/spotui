import type {
  EntityDetail,
  ProblemDetails,
  ProblemIssue,
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
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { Accept: "application/json" },
      ...init,
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
