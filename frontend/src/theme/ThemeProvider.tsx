import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { applyTheme, readStoredTheme } from "./apply-theme";
import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  type ThemeOption,
} from "./themes";

type ThemeContextValue = {
  theme: ThemeOption;
  setTheme: (theme: ThemeOption) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeOption>(() => {
    if (typeof document === "undefined") {
      return DEFAULT_THEME;
    }

    const initial = readStoredTheme(THEME_STORAGE_KEY);
    applyTheme(initial);
    return initial;
  });

  const setTheme = useCallback((next: ThemeOption) => {
    applyTheme(next);
    setThemeState(next);

    try {
      localStorage.setItem(THEME_STORAGE_KEY, next.id);
    } catch {
      // Ignore persistence failures.
    }
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme }),
    [theme, setTheme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
