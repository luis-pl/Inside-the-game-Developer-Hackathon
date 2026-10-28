import { Icon } from "./Icon.tsx";
import type { Theme } from "../hooks/use-theme.ts";

export function ThemeToggle({
  theme,
  onToggle,
  className = "theme-switch",
}: {
  theme: Theme;
  onToggle: () => void;
  className?: string;
}) {
  const label =
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  return (
    <button
      type="button"
      className={className}
      onClick={onToggle}
      aria-label={label}
      title={label}
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} />
      <span>{theme === "dark" ? "Light appearance" : "Dark appearance"}</span>
    </button>
  );
}
