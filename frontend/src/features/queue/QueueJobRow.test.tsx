import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QueueJob } from "../../api/types";
import { QueueJobRow } from "./QueueJobRow";

const base: QueueJob = {
  id: "job-1",
  url: "https://music.amazon.com/tracks/B002TRACK1",
  title: "Tum Hi Ho",
  artist: "Arijit Singh",
  state: "running",
  status_message: "downloading…",
  progress_phase: "downloading",
  attempt_count: 1,
  created_at: 1_700_000_000,
  updated_at: 1_700_000_100,
};

describe("QueueJobRow", () => {
  it("shows active phase text and an indeterminate bar, not a percentage", () => {
    render(<QueueJobRow job={base} onCancel={vi.fn()} />);

    expect(screen.getByText("downloading…")).toBeInTheDocument();
    expect(screen.getByLabelText("Cancel download Tum Hi Ho")).toBeEnabled();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows failed details and retries", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    const job: QueueJob = {
      ...base,
      state: "failed",
      status_message: "download failed",
      last_error: "The downloader finished without a success summary.",
    };

    render(<QueueJobRow job={job} onRetry={retry} />);

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(
      screen.getByText("The downloader finished without a success summary."),
    ).toBeInTheDocument();
    await user.click(screen.getByLabelText("Retry download Tum Hi Ho"));
    expect(retry).toHaveBeenCalledWith(job);
  });

  it("shows completed output without retrying", () => {
    const job: QueueJob = {
      ...base,
      state: "completed",
      status_message: "saved",
      output_path: "Artists/Arijit Singh/Aashiqui 2/Tum Hi Ho.flac",
    };

    render(<QueueJobRow job={job} />);

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Tum Hi Ho.flac")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
