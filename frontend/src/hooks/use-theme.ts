import { useEffect, useLayoutEffect, useState } from "react";
import "../theme.css";

export type Theme = "light" | "dark";
const KEY = "inside-game-theme";
function readTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** One appearance preference for the workspace, embedded report and viewer. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      // Appearance still works when browser storage is unavailable.
    }
  }, [theme]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === KEY || event.key === null) setTheme(readTheme());
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  return {
    theme,
    toggleTheme: () =>
      setTheme((value) => (value === "dark" ? "light" : "dark")),
  };
}
