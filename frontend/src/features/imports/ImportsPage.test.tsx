import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AmazonCandidate,
  ImportSessionDetail,
  ImportSourceTrack,
} from "../../api/types";
import { useSnackbarStore } from "../../state/snackbarStore";
import { useUIStore } from "../../state/uiStore";
import { ImportsPage } from "./ImportsPage";

const candidate: AmazonCandidate = {
  id: "candidate-1",
  url: "https://music.amazon.com/tracks/B000000001",
  track_key: "amazon:B000000001",
  title: "Candidate Song",
  artist: "Artist",
  album: "",
  duration_seconds: null,
  artwork_url: null,
  provider_position: 0,
  rank: 1,
  score: 0.95,
  explanation: "Exact title with a matching artist",
};

function source(overrides: Partial<ImportSourceTrack> = {}): ImportSourceTrack {
  return {
    id: "source-1",
    position: 0,
    spotify_track_id: "2222222222222222222221",
    source_url: "https://open.spotify.com/track/2222222222222222222221",
    title: "Source Song",
    artist: "Source Artist",
    duration_seconds: 180,
    matching_status: "candidates_ready",
    review_status: "unreviewed",
    selected_candidate_id: null,
    library_match: null,
    queue_outcome: "none",
    queued_job_id: null,
    source_duplicate_of_id: null,
    queued_duplicate_of_source_id: null,
    attempt_count: 1,
    last_error: null,
    candidates: [candidate],
    ...overrides,
  };
}

function detail(overrides: Partial<ImportSessionDetail> = {}): ImportSessionDetail {
  const base: ImportSessionDetail = {
    id: "session-1",
    source_url: "https://open.spotify.com/playlist/1111111111111111111111",
    spotify_type: "playlist",
    spotify_id: "1111111111111111111111",
    title: "Road Trip",
    artwork_url: null,
    status: "matching",
    revision: 8,
    counts: {
      total: 1,
      pending: 0,
      searching: 0,
      matched: 1,
      no_results: 0,
      failed: 0,
      selected: 0,
      queued: 0,
      duplicate: 0,
      skipped: 0,
      library_skipped: 0,
      unresolved: 1,
    },
    last_error: null,
    created_at: 1_700_000_000,
    updated_at: 1_700_000_100,
    matching_started_at: 1_700_000_000,
    matching_completed_at: null,
    sources: [source()],
  };
  return { ...base, ...overrides };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  useUIStore.getState().reset();
  useSnackbarStore.getState().reset();
  vi.unstubAllGlobals();
  vi.stubGlobal(
    "EventSource",
    class {
      addEventListener() {}
      close() {}
    },
  );
});

describe("ImportsPage", () => {
  it("requires an explicit candidate selection before queueing", async () => {
    let current = detail();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/imports" && (!init || init.method === undefined)) {
        return jsonResponse({ imports: [current] });
      }
      if (url === "/api/v1/imports/session-1" && (!init || init.method === undefined)) {
        return jsonResponse(current);
      }
      if (url.endsWith("/sources/source-1/select")) {
        current = detail({
          revision: 9,
          counts: { ...current.counts, selected: 1, unresolved: 0 },
          sources: [
            source({
              review_status: "selected",
              selected_candidate_id: "candidate-1",
            }),
          ],
        });
        return jsonResponse(current);
      }
      if (url.endsWith("/enqueue")) {
        current = detail({
          revision: 10,
          counts: {
            ...current.counts,
            selected: 1,
            queued: 1,
            unresolved: 0,
          },
          sources: [
            source({
              review_status: "selected",
              selected_candidate_id: "candidate-1",
              queue_outcome: "queued",
              queued_job_id: "job-1",
            }),
          ],
        });
        return jsonResponse({
          session: current,
          queued: 1,
          duplicate: 0,
          skipped_library: 0,
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ImportsPage />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { level: 2, name: "Road Trip" }),
    ).toBeInTheDocument();
    const addButton = screen.getByRole("button", {
      name: /Add selected to queue \(0\)/,
    });
    expect(addButton).toBeDisabled();

    const candidateButton = screen.getByRole("button", {
      name: /Candidate Song/,
    });
    expect(candidateButton).toHaveAttribute("aria-pressed", "false");
    await user.click(candidateButton);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Candidate Song/ }),
      ).toHaveAttribute("aria-pressed", "true");
    });
    const enabledAdd = screen.getByRole("button", {
      name: /Add selected to queue \(1\)/,
    });
    expect(enabledAdd).toBeEnabled();
    await user.click(enabledAdd);

    await waitFor(() => {
      expect(screen.getAllByText("Queued").length).toBeGreaterThan(0);
    });
    expect(
      fetchMock.mock.calls.some(
        ([url]) => String(url) === "/api/v1/imports/session-1/enqueue",
      ),
    ).toBe(true);
    const enqueueCall = fetchMock.mock.calls.find(
      ([url]) => String(url) === "/api/v1/imports/session-1/enqueue",
    );
    expect(JSON.parse(String((enqueueCall?.[1] as RequestInit).body))).toEqual({
      force_library: false,
    });
  });

  it("shows a persistent creation error with the request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/imports" && (!init || init.method === undefined)) {
          return jsonResponse({ imports: [detail()] });
        }
        if (url === "/api/v1/imports") {
          return new Response(
            JSON.stringify({
              type: "urn:spotui:error:active_import_conflict",
              title: "Import already active",
              status: 409,
              detail: "Another Spotify import is already active.",
              code: "active_import_conflict",
              request_id: "req-import",
            }),
            {
              status: 409,
              headers: { "content-type": "application/problem+json" },
            },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ImportsPage />
      </QueryClientProvider>,
    );

    await user.type(
      await screen.findByLabelText(/Import a public Spotify album or playlist/),
      "https://open.spotify.com/playlist/1111111111111111111111",
    );
    await user.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByText("Another Spotify import is already active.")).toBeInTheDocument();
    expect(screen.getByText(/req-import/)).toBeInTheDocument();
  });
});
