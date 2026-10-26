export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "spotui-theme";

function isThemePreference(value: string | null): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

export function applyThemePreference(preference: ThemePreference): void {
  let dark = preference === "dark";
  if (preference === "system") {
    dark =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage can be disabled; the theme still applies for this session.
  }
  applyThemePreference(preference);
}

export function initializeTheme(): void {
  applyThemePreference(readThemePreference());
  if (typeof window.matchMedia !== "function") {
    return;
  }
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (readThemePreference() === "system") {
        applyThemePreference("system");
      }
    });
}
