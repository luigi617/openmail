import type { ThemeMode, ThemeName } from "./theme";
import { themes } from "./theme";
import { getSystemTheme } from "./systemTheme";

export function applyTheme(mode: ThemeMode): ThemeName {
  const resolvedTheme: ThemeName =
    mode === "system" ? getSystemTheme() : mode;

  const root = document.documentElement;
  const tokens = themes[resolvedTheme];

  root.setAttribute("data-theme", resolvedTheme);

  Object.entries(tokens).forEach(([key, value]) => {
    root.style.setProperty(`--${camelToKebab(key)}`, value);
  });

  return resolvedTheme;
}

function camelToKebab(str: string) {
  return str.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
}
