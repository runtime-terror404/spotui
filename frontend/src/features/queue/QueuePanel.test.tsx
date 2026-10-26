import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { QueueSnapshot } from "../../api/types";
import { QueuePanel } from "./QueuePanel";

const state: { snapshot: QueueSnapshot | undefined } = { snapshot: undefined };

vi.mock("./hooks", () => ({
  useQueue: () => ({
    data: state.snapshot,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  }),
  useCancelJob: () => ({ isPending: false, mutate: vi.fn() }),
  useRetryJob: () => ({ isPending: false, mutate: vi.fn() }),
  useDismissJob: () => ({ isPending: false, mutate: vi.fn() }),
}));

afterEach(() => {
  vi.useRealTimers();
});

describe("QueuePanel", () => {
  it("removes a completed job shortly after completion", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-26T16:00:00Z"));
    const completedAt = Math.floor(Date.now() / 1000);
    state.snapshot = {
      jobs: [
        {
          id: "done",
          url: "https://music.amazon.com/tracks/B002TRACK1",
          title: "Tum Hi Ho",
          artist: "Arijit Singh",
          state: "completed",
          status_message: "saved",
          attempt_count: 1,
          output_path: "Artists/Arijit Singh/Tum Hi Ho.flac",
          created_at: completedAt - 10,
          updated_at: completedAt,
          completed_at: completedAt,
        },
      ],
      counts: {
        queued: 0,
        active: 0,
        completed: 1,
        failed: 0,
        cancelled: 0,
        interrupted: 0,
      },
    };

    render(<QueuePanel />);

    expect(screen.getByText("Tum Hi Ho")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(3_500);
    });

    expect(screen.queryByText("Tum Hi Ho")).not.toBeInTheDocument();
    expect(screen.getByText("No active downloads.")).toBeInTheDocument();
  });

  it("hides a cancelled waiting job immediately", () => {
    const cancelledAt = Math.floor(Date.now() / 1000);
    state.snapshot = {
      jobs: [
        {
          id: "cancelled",
          url: "https://music.amazon.com/tracks/B002TRACK1",
          title: "Tum Hi Ho",
          artist: "Arijit Singh",
          state: "cancelled",
          status_message: "cancelled",
          attempt_count: 0,
          created_at: cancelledAt - 10,
          updated_at: cancelledAt,
          completed_at: cancelledAt,
        },
      ],
      counts: {
        queued: 0,
        active: 0,
        completed: 0,
        failed: 0,
        cancelled: 1,
        interrupted: 0,
      },
    };

    render(<QueuePanel />);

    expect(screen.queryByText("Tum Hi Ho")).not.toBeInTheDocument();
    expect(screen.getByText("No active downloads.")).toBeInTheDocument();
  });
});
