import { DEFAULT_THEME, isTheme, type Theme } from "./themes";

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = "light";
}

export function readStoredTheme(storageKey: string): Theme {
  try {
    const stored = localStorage.getItem(storageKey);
    if (isTheme(stored)) {
      return stored;
    }
  } catch {
    // Private mode / blocked storage — keep the default.
  }

  return DEFAULT_THEME;
}
