import { isTheme, THEME_LABELS, THEMES } from "./themes";
import { useTheme } from "./ThemeProvider";

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  return (
    <label className="theme-switcher">
      <span className="theme-switcher__label">Theme</span>
      <select
        className="theme-switcher__select"
        value={theme}
        onChange={(event) => {
          if (isTheme(event.target.value)) {
            setTheme(event.target.value);
          }
        }}
      >
        {THEMES.map((option) => (
          <option key={option} value={option}>
            {THEME_LABELS[option]}
          </option>
        ))}
      </select>
    </label>
  );
}
