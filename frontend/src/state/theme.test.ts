import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  THEME_STORAGE_KEY,
  applyThemePreference,
  readThemePreference,
  setThemePreference,
} from "./theme";

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("theme preference", () => {
  it("persists explicit light and dark choices", () => {
    setThemePreference("light");
    expect(readThemePreference()).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");

    setThemePreference("dark");
    expect(readThemePreference()).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("resolves system theme from the media query", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );

    setThemePreference("system");

    expect(readThemePreference()).toBe("system");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyThemePreference("system");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
