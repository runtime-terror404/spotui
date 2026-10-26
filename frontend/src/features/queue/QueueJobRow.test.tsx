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
  it("uses an icon-only cancel action for active downloads", async () => {
    const user = userEvent.setup();
    const cancel = vi.fn();
    render(<QueueJobRow job={base} onCancel={cancel} />);

    expect(screen.getByText("downloading…")).toBeInTheDocument();
    expect(screen.queryByText("Cancel")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Cancel download Tum Hi Ho"));
    expect(cancel).toHaveBeenCalledWith(base);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("uses a compact title and artist summary for waiting jobs", async () => {
    const user = userEvent.setup();
    const dismiss = vi.fn();
    const job: QueueJob = {
      ...base,
      state: "queued",
      status_message: "queued",
      attempt_count: 0,
    };

    const { container } = render(
      <QueueJobRow job={job} onDismiss={dismiss} />,
    );

    expect(screen.queryByText("Waiting")).not.toBeInTheDocument();
    expect(container.querySelector(".queue-job__summary")).toHaveTextContent(
      /Tum Hi Ho\s*\|\s*Arijit Singh/,
    );
    await user.click(
      screen.getByLabelText("Cancel queued download Tum Hi Ho"),
    );
    expect(dismiss).toHaveBeenCalledWith(job);
  });

  it("hides the failed label but keeps details, retry, and dismiss", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    const dismiss = vi.fn();
    const job: QueueJob = {
      ...base,
      state: "failed",
      status_message: "download failed",
      last_error: "The downloader finished without a success summary.",
    };

    render(
      <QueueJobRow job={job} onRetry={retry} onDismiss={dismiss} />,
    );

    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
    expect(
      screen.getByText("The downloader finished without a success summary."),
    ).toBeInTheDocument();
    await user.click(screen.getByLabelText("Retry download Tum Hi Ho"));
    expect(retry).toHaveBeenCalledWith(job);
    await user.click(
      screen.getByLabelText("Dismiss failed download Tum Hi Ho"),
    );
    expect(dismiss).toHaveBeenCalledWith(job);
  });

  it("hides the completed label and keeps the downloaded filename", () => {
    const job: QueueJob = {
      ...base,
      state: "completed",
      status_message: "saved",
      output_path: "Artists/Arijit Singh/Aashiqui 2/Tum Hi Ho.flac",
    };

    render(<QueueJobRow job={job} />);

    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
    expect(screen.getByText("Tum Hi Ho.flac")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
