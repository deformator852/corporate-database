import {DEFAULT_THEME, findTheme, type ThemeOption} from "./themes";

export function applyTheme(theme: ThemeOption) {
  const root = document.documentElement;
  root.dataset.theme = theme.id;
  root.classList.toggle("dark", theme.dark === true);
  root.style.colorScheme = theme.dark ? "dark" : "light";
}

export function readStoredTheme(storageKey: string): ThemeOption {
  try {
    const stored = findTheme(localStorage.getItem(storageKey));
    if (stored) {
      return stored;
    }
  } catch {
    // Private mode / blocked storage — keep the default.
  }

  return DEFAULT_THEME;
}
