export type ThemeName = "light" | "dark";
export type ThemeMode = ThemeName | "system";

export type ThemeTokens = {
  background: string;
  backgroundSoft: string;
  text: string;
  textMuted: string;
  border: string;
  primary: string;
};

export const themes: Record<ThemeName, ThemeTokens> = {
  light: {
    background: "#ffffff",
    backgroundSoft: "#f6f7f9",
    text: "#1f2937",
    textMuted: "#6b7280",
    border: "#e5e7eb",
    primary: "#2563eb",
  },

  dark: {
    background: "#0f172a",
    backgroundSoft: "#020617",
    text: "#e5e7eb",
    textMuted: "#94a3b8",
    border: "#1e293b",
    primary: "#60a5fa",
  },
};
