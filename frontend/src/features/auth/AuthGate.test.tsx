import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "./AuthGate";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

function renderGate() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthGate>
        <p>Private application</p>
      </AuthGate>
    </QueryClientProvider>,
  );
}

describe("AuthGate", () => {
  it("renders the app directly on the local host", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          local: true,
          authenticated: true,
          pairing_required: false,
          lan_available: false,
        }),
      ),
    );

    renderGate();

    expect(await screen.findByText("Private application")).toBeInTheDocument();
    expect(screen.queryByText("Pair this browser")).not.toBeInTheDocument();
  });

  it("pairs an unauthenticated LAN browser before showing the app", async () => {
    let paired = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/auth/status") {
        return jsonResponse({
          local: false,
          authenticated: paired,
          pairing_required: !paired,
          lan_available: true,
          lan_url: "http://192.168.1.10:8765",
          device: paired ? { id: "device-1", label: "Phone" } : null,
        });
      }
      if (url === "/api/v1/auth/pair") {
        paired = true;
        return jsonResponse({
          local: false,
          authenticated: true,
          pairing_required: false,
          lan_available: true,
          lan_url: "http://192.168.1.10:8765",
          device: { id: "device-1", label: "Phone" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderGate();

    expect(
      await screen.findByRole("heading", { name: "Pair this browser" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/plain HTTP/)).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Six-digit pairing code"),
      "123456",
    );
    await user.type(screen.getByLabelText("Device name (optional)"), "Phone");
    await user.click(screen.getByRole("button", { name: "Pair browser" }));

    expect(await screen.findByText("Private application")).toBeInTheDocument();
    const pairCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/api/v1/auth/pair"),
    );
    expect(pairCall).toBeDefined();
    expect(JSON.parse(String((pairCall?.[1] as RequestInit).body))).toEqual({
      code: "123456",
      label: "Phone",
    });
  });
});
