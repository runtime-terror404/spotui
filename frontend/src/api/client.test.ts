import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiProblem,
  NetworkProblem,
  cancelQueueJob,
  enqueueTrack,
  fetchEntityDetail,
  fetchNowPlaying,
  fetchQueue,
  searchAmazon,
} from "./client";

function jsonResponse(body: unknown, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": contentType },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("searchAmazon", () => {
  it("encodes the query and returns typed data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ query: "arijit singh", sections: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await searchAmazon("arijit singh");

    expect(result.query).toBe("arijit singh");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/search?q=arijit+singh",
      expect.anything(),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).get("Accept")).toBe("application/json");
  });

  it("maps problem+json errors to ApiProblem", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            type: "urn:spotui:error:amazon_unavailable",
            title: "Amazon Music unavailable",
            status: 503,
            detail: "The browser runtime is unavailable.",
            code: "amazon_unavailable",
            request_id: "req-123",
          },
          503,
          "application/problem+json",
        ),
      ),
    );

    await expect(searchAmazon("x")).rejects.toMatchObject({
      status: 503,
      code: "amazon_unavailable",
      requestId: "req-123",
      message: "The browser runtime is unavailable.",
    });
  });

  it("maps network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(searchAmazon("x")).rejects.toBeInstanceOf(NetworkProblem);
  });

  it("falls back for non-problem HTTP errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("no", { status: 404 })));

    const error = await searchAmazon("x").catch((value: unknown) => value);
    expect(error).toBeInstanceOf(ApiProblem);
    expect(error).toMatchObject({ status: 404, code: "http_error" });
  });
});

describe("fetchEntityDetail", () => {
  it("encodes the Amazon URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ kind: "album", title: "Album", subtitle: "", tracks: [], albums: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchEntityDetail("https://music.amazon.in/albums/B001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/entities/detail?url=https%3A%2F%2Fmusic.amazon.in%2Falbums%2FB001",
      expect.anything(),
    );
  });
});

describe("now playing", () => {
  it("fetches current MPRIS metadata", async () => {
    const payload = {
      available: true,
      track: { title: "Song", artist: "Artist" },
      player: "spotify",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchNowPlaying()).toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/now-playing",
      expect.anything(),
    );
  });
});

describe("queue endpoints", () => {
  it("fetches the queue snapshot", async () => {
    const snapshot = {
      jobs: [],
      counts: {
        queued: 0,
        active: 0,
        completed: 0,
        failed: 0,
        cancelled: 0,
        interrupted: 0,
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(snapshot));
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchQueue()).toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/queue", expect.anything());
  });

  it("posts an enqueue request as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        job: { id: "job-1", title: "Song", artist: "Artist", state: "queued" },
        duplicate: false,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await enqueueTrack({
      url: "https://music.amazon.com/tracks/B002TRACK1",
      title: "Song",
      artist: "Artist",
    });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/queue/jobs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      url: "https://music.amazon.com/tracks/B002TRACK1",
      title: "Song",
      artist: "Artist",
    });
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("encodes job IDs for cancel", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "a b" }));
    vi.stubGlobal("fetch", fetchMock);

    await cancelQueueJob("a b");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/queue/jobs/a%20b/cancel",
    );
  });
});
