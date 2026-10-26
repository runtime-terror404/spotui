import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiProblem, NetworkProblem, fetchEntityDetail, searchAmazon } from "./client";

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
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
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
