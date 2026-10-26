import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";

beforeEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  it("shows the code, LAN URL, HTTP warning, and paired devices locally", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/v1/auth/status") {
        return jsonResponse({
          local: true,
          authenticated: true,
          pairing_required: false,
          lan_available: true,
          lan_url: "http://192.168.1.10:8765",
        });
      }
      if (url === "/api/v1/devices/pairing") {
        return jsonResponse({
          code: "123456",
          lan_available: true,
          lan_url: "http://192.168.1.10:8765",
        });
      }
      if (url === "/api/v1/devices") {
        return jsonResponse({
          devices: [
            {
              id: "device-1",
              label: "My phone",
              created_at: 1_700_000_000,
              last_seen_at: 1_700_000_100,
              last_seen_ip: "192.168.1.20",
            },
          ],
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettings();

    expect(await screen.findByText("123456")).toBeInTheDocument();
    expect(screen.getByText("http://192.168.1.10:8765")).toBeInTheDocument();
    expect(screen.getByText(/LAN traffic is not encrypted/)).toBeInTheDocument();
    expect(await screen.findByText("My phone")).toBeInTheDocument();
    expect(screen.getByText("Last seen from 192.168.1.20")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument();
  });

  it("does not request the pairing code or devices from a LAN browser", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/v1/auth/status") {
        return jsonResponse({
          local: false,
          authenticated: true,
          pairing_required: false,
          lan_available: true,
          lan_url: "http://192.168.1.10:8765",
          device: { id: "device-1", label: "My phone" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettings();

    expect(
      await screen.findByText(/Device management and the pairing code are available only/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Pairing code")).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).startsWith("/api/v1/devices"),
      ),
    ).toBe(false);
  });
});
