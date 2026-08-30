import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

const STORAGE_KEY = "ocean-theme";
const LEGACY_KEYS = ["mercari-global-theme"];  // one-shot migration of pre-rebrand pref
const ThemeContext = createContext({ theme: "light", toggleTheme: () => {}, setTheme: () => {} });

const applyClass = (t) => {
  const root = document.documentElement;
  if (t === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
  root.style.colorScheme = t;
};

export const ThemeProvider = ({ children }) => {
  const [theme, setThemeState] = useState(() => {
    if (typeof window === "undefined") return "light";
    let saved = window.localStorage.getItem(STORAGE_KEY);
    // One-shot migration from pre-rebrand keys
    if (!saved) {
      for (const k of LEGACY_KEYS) {
        const v = window.localStorage.getItem(k);
        if (v) { saved = v; window.localStorage.removeItem(k); break; }
      }
    }
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    applyClass(theme);
    try { window.localStorage.setItem(STORAGE_KEY, theme); } catch (_) { /* noop */ }
  }, [theme]);

  const setTheme = useCallback((t) => setThemeState(t === "dark" ? "dark" : "light"), []);
  const toggleTheme = useCallback(() => setThemeState((p) => (p === "dark" ? "light" : "dark")), []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
