import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueJob, QueueSnapshot } from "../../api/types";
import { QueuePage } from "./QueuePage";

const state: { snapshot: QueueSnapshot | undefined } = { snapshot: undefined };
const actions = vi.hoisted(() => ({
  cancel: vi.fn(),
  dismiss: vi.fn(),
  retry: vi.fn(),
}));

vi.mock("./hooks", () => ({
  useQueue: () => ({
    data: state.snapshot,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  }),
  useCancelJob: () => ({ isPending: false, mutate: actions.cancel }),
  useRetryJob: () => ({ isPending: false, mutate: actions.retry }),
  useDismissJob: () => ({ isPending: false, mutate: actions.dismiss }),
}));

const base: QueueJob = {
  id: "job",
  url: "https://music.amazon.com/tracks/B002TRACK1",
  title: "Tum Hi Ho",
  artist: "Arijit Singh",
  state: "queued",
  status_message: "queued",
  attempt_count: 0,
  created_at: 1_700_000_000,
  updated_at: 1_700_000_000,
};

function counts(overrides: Partial<QueueSnapshot["counts"]> = {}) {
  return {
    queued: 0,
    active: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
    interrupted: 0,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.snapshot = undefined;
});

describe("QueuePage", () => {
  it("renders only the newest 50 history rows while keeping the total count", () => {
    const completed = Array.from({ length: 51 }, (_, index) => {
      const number = 51 - index;
      return {
        ...base,
        id: `completed-${number}`,
        title: `Track ${String(number).padStart(2, "0")}`,
        state: "completed" as const,
        status_message: "saved",
        output_path: `Artists/Artist/Track ${number}.flac`,
        completed_at: 1_700_000_100 - index,
      };
    });
    state.snapshot = {
      jobs: completed,
      counts: counts({ completed: 51 }),
    };

    render(<QueuePage />);

    expect(screen.getAllByRole("article")).toHaveLength(50);
    expect(screen.getByText("Track 51")).toBeInTheDocument();
    expect(screen.queryByText("Track 01")).not.toBeInTheDocument();
    expect(
      screen.getByText("Completed").closest(".queue-count"),
    ).toHaveTextContent("51");
    expect(
      screen.getByRole("heading", { name: "History" }).parentElement,
    ).toHaveTextContent("50");
  });

  it("does not show cancelled jobs as history", () => {
    state.snapshot = {
      jobs: [
        {
          ...base,
          id: "cancelled",
          state: "cancelled",
          status_message: "cancelled",
        },
      ],
      counts: counts({ cancelled: 1 }),
    };

    render(<QueuePage />);

    expect(screen.queryByText("Tum Hi Ho")).not.toBeInTheDocument();
    expect(screen.getByText("No downloads yet")).toBeInTheDocument();
  });

  it("uses the X action to dismiss queued and failed jobs", async () => {
    const user = userEvent.setup();
    const queued = { ...base, id: "queued" };
    const failed: QueueJob = {
      ...base,
      id: "failed",
      title: "Failed Song",
      state: "failed",
      status_message: "download failed",
      last_error: "Download failed.",
    };
    state.snapshot = {
      jobs: [queued, failed],
      counts: counts({ queued: 1, failed: 1 }),
    };

    render(<QueuePage />);

    await user.click(screen.getByLabelText("Cancel queued download Tum Hi Ho"));
    expect(actions.dismiss).toHaveBeenCalledWith(queued);

    await user.click(screen.getByLabelText("Dismiss failed download Failed Song"));
    expect(actions.dismiss).toHaveBeenCalledWith(failed);
  });
});
