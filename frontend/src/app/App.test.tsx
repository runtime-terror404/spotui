import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useUIStore } from "../state/uiStore";
import { App } from "./App";

const searchData = {
  query: "arijit",
  sections: [
    {
      title: "Artists",
      kind: "artist",
      items: [
        {
          title: "Arijit Singh",
          subtitle: "Artist",
          url: "https://music.amazon.in/artists/B006ZO8YNU/arijit-singh",
          kind: "artist",
          image: "https://images.example/arijit.jpg",
        },
      ],
    },
  ],
};

const detailData = {
  kind: "artist",
  title: "Arijit Singh",
  subtitle: "",
  image: "https://images.example/arijit.jpg",
  tracks: [
    {
      title: "Tum Hi Ho",
      artist: "Arijit Singh",
      url: "https://music.amazon.com/tracks/B002TRACK",
    },
  ],
  albums: [],
};

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUIStore.getState().reset();
  vi.unstubAllGlobals();
});

describe("App search and details flow", () => {
  it("searches, opens an artist detail, and returns to the preserved search", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/v1/search")) {
        return new Response(JSON.stringify(searchData), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (url.startsWith("/api/v1/entities/detail")) {
        return new Response(JSON.stringify(detailData), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderApp();
    expect(
      screen.getByRole("heading", { name: "Search Amazon Music" }),
    ).toBeInTheDocument();

    const input = screen.getByRole("searchbox", { name: "Search Amazon Music" });
    await user.type(input, "arijit{Enter}");

    const artistCard = await screen.findByRole("button", {
      name: "Open Artist Arijit Singh",
    });
    expect(screen.getByText(/Results for/)).toBeInTheDocument();

    await user.click(artistCard);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Arijit Singh" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Tum Hi Ho")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to search" }));

    expect(
      await screen.findByRole("button", { name: "Open Artist Arijit Singh" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows a persistent search error with a retry action", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          type: "urn:spotui:error:amazon_unavailable",
          title: "Amazon Music unavailable",
          status: 503,
          detail: "The browser runtime is unavailable.",
          code: "amazon_unavailable",
          request_id: "req-503",
        }),
        {
          status: 503,
          headers: { "content-type": "application/problem+json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderApp();
    await user.type(
      screen.getByRole("searchbox", { name: "Search Amazon Music" }),
      "arijit{Enter}",
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The browser runtime is unavailable.",
    );
    expect(screen.getByText(/req-503/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
