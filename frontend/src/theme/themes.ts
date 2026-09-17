export const THEMES = ["neutral", "slate"] as const;

export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = "neutral";
export const THEME_STORAGE_KEY = "ui-theme";

export const THEME_LABELS: Record<Theme, string> = {
  neutral: "Neutral",
  slate: "Slate",
};

export function isTheme(value: string | null): value is Theme {
  return THEMES.includes(value as Theme);
}
