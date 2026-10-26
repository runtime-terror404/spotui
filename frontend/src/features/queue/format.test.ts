import { describe, expect, it } from "vitest";

import type { QueueJob } from "../../api/types";
import {
  COMPACT_COMPLETED_HOLD_SECONDS,
  HISTORY_LIMIT,
  compactQueueJobs,
  historyQueueJobs,
} from "./format";

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

describe("compactQueueJobs", () => {
  it("keeps non-completed jobs and only recently completed jobs", () => {
    const active = { ...base, id: "active", state: "running" as const };
    const waiting = { ...base, id: "waiting" };
    const recent = {
      ...base,
      id: "recent",
      state: "completed" as const,
      completed_at: 1_700_000_010,
    };
    const old = {
      ...base,
      id: "old",
      state: "completed" as const,
      completed_at: 1_700_000_000,
    };

    const visible = compactQueueJobs(
      [active, waiting, recent, old],
      1_700_000_010 + COMPACT_COMPLETED_HOLD_SECONDS - 1,
    );

    expect(visible.map((job) => job.id)).toEqual(["active", "waiting", "recent"]);
  });

  it("keeps a just-completed job visible for the hold window", () => {
    const completed = {
      ...base,
      id: "completed",
      state: "completed" as const,
      completed_at: 1_700_000_010,
    };

    expect(compactQueueJobs([completed], 1_700_000_011)).toEqual([completed]);
    expect(compactQueueJobs([completed], 1_700_000_014)).toEqual([]);
  });

  it("uses the update time when completed_at is absent", () => {
    const completed = {
      ...base,
      id: "completed",
      state: "completed" as const,
      updated_at: 1_700_000_005,
    };

    expect(compactQueueJobs([completed], 1_700_000_006)).toEqual([completed]);
    expect(compactQueueJobs([completed], 1_700_000_009)).toEqual([]);
  });

  it("removes cancelled jobs immediately regardless of completion time", () => {
    const cancelled = {
      ...base,
      id: "cancelled",
      state: "cancelled" as const,
      completed_at: 1_700_000_009,
    };

    expect(compactQueueJobs([cancelled], 1_700_000_010)).toEqual([]);
  });
});

describe("historyQueueJobs", () => {
  it("keeps only the newest completed jobs up to the history limit", () => {
    const completed = Array.from(
      { length: HISTORY_LIMIT + 5 },
      (_, index): QueueJob => ({
        ...base,
        id: `completed-${index}`,
        title: `Song ${index}`,
        state: "completed",
        completed_at: 1_700_000_100 - index,
      }),
    );
    const cancelled: QueueJob = {
      ...base,
      id: "cancelled",
      state: "cancelled",
      completed_at: 1_700_000_101,
    };

    const history = historyQueueJobs([cancelled, ...completed]);

    expect(history).toHaveLength(HISTORY_LIMIT);
    expect(history.map((job) => job.id)).toEqual(
      completed.slice(0, HISTORY_LIMIT).map((job) => job.id),
    );
    expect(history.some((job) => job.state === "cancelled")).toBe(false);
  });
});
