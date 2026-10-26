import { beforeEach, describe, expect, it } from "vitest";

import { useUIStore } from "./uiStore";

beforeEach(() => {
  useUIStore.getState().reset();
});

describe("uiStore", () => {
  it("submits a trimmed search and opens a detail view", () => {
    useUIStore.getState().setInputQuery("  arijit singh ");
    useUIStore.getState().submitSearch("  arijit singh ");
    expect(useUIStore.getState().submittedQuery).toBe("arijit singh");
    expect(useUIStore.getState().view).toBe("search");

    useUIStore.getState().setSearchScrollY(420);
    useUIStore.getState().openDetail("https://music.amazon.in/artists/B1");
    expect(useUIStore.getState().view).toBe("detail");
    expect(useUIStore.getState().detailUrl).toBe("https://music.amazon.in/artists/B1");

    useUIStore.getState().backToSearch();
    expect(useUIStore.getState().view).toBe("search");
    expect(useUIStore.getState().detailUrl).toBeNull();
    expect(useUIStore.getState().searchScrollY).toBe(420);
  });

  it("ignores empty submissions", () => {
    useUIStore.getState().submitSearch("   ");

    expect(useUIStore.getState().submittedQuery).toBe("");
  });

  it("clears detail state when starting a new search", () => {
    useUIStore.getState().openDetail("https://music.amazon.in/albums/B1");
    useUIStore.getState().submitSearch("new query");

    expect(useUIStore.getState().detailUrl).toBeNull();
    expect(useUIStore.getState().view).toBe("search");
    expect(useUIStore.getState().searchScrollY).toBe(0);
  });

  it("switches between search and queue without losing the query", () => {
    useUIStore.getState().submitSearch("arijit");
    useUIStore.getState().openQueue();
    expect(useUIStore.getState().view).toBe("queue");

    useUIStore.getState().openSearch();
    expect(useUIStore.getState().view).toBe("search");
    expect(useUIStore.getState().submittedQuery).toBe("arijit");
  });

  it("opens imports with an optional selected session", () => {
    useUIStore.getState().openImports("session-1");
    expect(useUIStore.getState().view).toBe("imports");
    expect(useUIStore.getState().selectedImportId).toBe("session-1");

    useUIStore.getState().openImports();
    expect(useUIStore.getState().selectedImportId).toBeNull();
  });

  it("opens settings", () => {
    useUIStore.getState().openSettings();
    expect(useUIStore.getState().view).toBe("settings");
  });
});
