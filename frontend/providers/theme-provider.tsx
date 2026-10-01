"use client";

import * as React from "react";

export type Theme = "light" | "dark" | "system";
type Resolved = "light" | "dark";

const STORAGE_KEY = "theme";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: Resolved;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function systemTheme(): Resolved {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readStored(fallback: Theme): Theme {
  if (typeof window === "undefined") return fallback;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" || v === "system" ? v : fallback;
  } catch {
    return fallback;
  }
}

function apply(resolved: Resolved) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

/**
 * Minimal theme provider: toggles the `dark` class on <html>, persists the
 * choice to localStorage, and follows the OS while set to "system".
 *
 * Replaces `next-themes`, whose provider renders an inline <script> on every
 * client render -- React 19's dev mode flags that ("Encountered a script tag
 * while rendering React component"). Here the anti-flash script is injected by
 * next/script (beforeInteractive) in the root layout, outside React's tree.
 */
export function ThemeProvider({
  children,
  defaultTheme = "dark",
}: {
  children: React.ReactNode;
  defaultTheme?: Theme;
}) {
  const [theme, setThemeState] = React.useState<Theme>(() => readStored(defaultTheme));
  // OS preference, updated only from the media-query change event (not an
  // effect body) so it stays out of the set-state-in-effect rule.
  const [systemPref, setSystemPref] = React.useState<Resolved>(() => systemTheme());

  const resolvedTheme: Resolved = theme === "system" ? systemPref : theme;

  // Reflect the resolved value onto <html>.
  React.useEffect(() => {
    apply(resolvedTheme);
  }, [resolvedTheme]);

  // Subscribe to the OS setting.
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemPref(mq.matches ? "dark" : "light");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Keep tabs in sync.
  React.useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setThemeState(readStored(defaultTheme));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [defaultTheme]);

  const setTheme = React.useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode / storage disabled -- theme just won't persist */
    }
  }, []);

  const value = React.useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme]
  );

  return <ThemeContext value={value}>{children}</ThemeContext>;
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  // A sensible default if ever used outside the provider (isolated tests, etc.).
  return ctx ?? { theme: "dark", resolvedTheme: "dark", setTheme: () => {} };
}

/**
 * Inline script for the server-rendered layout: applies the stored theme to
 * <html> before first paint so there's no flash of the wrong theme.
 */
export const THEME_INIT_SCRIPT = `try{var t=localStorage.getItem('${STORAGE_KEY}')||'dark';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);var e=document.documentElement;e.classList.toggle('dark',d);e.style.colorScheme=d?'dark':'light'}catch(e){}`;
