import {DEFAULT_THEME, findTheme, type ThemeOption} from "./themes";

export function applyTheme(theme: ThemeOption) {
  const root = document.documentElement;
  root.dataset.theme = theme.id;
  root.classList.toggle("dark", theme.dark === true);
  root.style.colorScheme = theme.dark ? "dark" : "light";
  try {
    // Read by public/theme-init.js before the app loads.
    localStorage.setItem("ui-theme-dark", theme.dark ? "1" : "0");
  } catch {
    // Private mode / blocked storage.
  }
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
