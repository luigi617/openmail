import type { ThemeName } from "./theme";

export function getSystemTheme(): ThemeName {
    console.log(window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light")
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function onSystemThemeChange(
  callback: (theme: ThemeName) => void
) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  const handler = (e: MediaQueryListEvent) => {
    callback(e.matches ? "dark" : "light");
  };

  media.addEventListener("change", handler);

  return () => media.removeEventListener("change", handler);
}
