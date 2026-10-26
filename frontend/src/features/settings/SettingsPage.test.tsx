import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { THEME_STORAGE_KEY } from "../../state/theme";
import { SettingsPage } from "./SettingsPage";

const systemInfo = {
  version: "0.1.0",
  root: "/home/test/.local/share/spotui",
  config_file: "/home/test/.local/share/spotui/config.toml",
  download_directory: "/mnt/Shared/Music",
  downloader_available: true,
};

const libraryOverview = {
  roots: [
    {
      id: 1,
      path: "/mnt/Shared/Music",
      available: true,
      index_complete: true,
      file_count: 1234,
      last_checked_at: 1_700_000_000,
      last_scan_at: 1_700_000_000,
    },
  ],
  active_scan: null,
  total_files: 1234,
  unavailable_roots: 0,
};

const queueSnapshot = {
  jobs: [],
  counts: {
    queued: 0,
    active: 0,
    completed: 12,
    failed: 0,
    cancelled: 0,
    interrupted: 0,
  },
};

beforeEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function mockSharedEndpoints(input: RequestInfo | URL): Response | undefined {
  const url = String(input);
  if (url === "/api/v1/system/info") {
    return jsonResponse(systemInfo);
  }
  if (url === "/api/v1/library") {
    return jsonResponse(libraryOverview);
  }
  if (url === "/api/v1/queue") {
    return jsonResponse(queueSnapshot);
  }
  return undefined;
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
  it("shows application info and stores an explicit theme choice", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const shared = mockSharedEndpoints(input);
      if (shared) {
        return shared;
      }
      if (String(input) === "/api/v1/auth/status") {
        return jsonResponse({
          local: true,
          authenticated: true,
          pairing_required: false,
          lan_available: false,
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderSettings();

    expect(
      await screen.findByText("Library & downloads"),
    ).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getAllByText("/mnt/Shared/Music").length).toBeGreaterThan(0);
    expect(screen.getByText("SpotUI 0.1.0")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "System" })).toBeChecked();

    await user.click(screen.getByRole("radio", { name: "Dark" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    await user.click(screen.getByRole("radio", { name: "Light" }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("shows the code, LAN URL, HTTP warning, and paired devices locally", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const shared = mockSharedEndpoints(input);
      if (shared) {
        return shared;
      }
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
      const shared = mockSharedEndpoints(input);
      if (shared) {
        return shared;
      }
      if (String(input) === "/api/v1/auth/status") {
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
