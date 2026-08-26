import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

/**
 * FontSizeContext — user-adjustable UI density.
 *
 * Under the hood we set `document.documentElement.style.fontSize` to a pixel
 * value; because every Tailwind size class uses `rem`, the whole UI scales
 * proportionally in one line — no per-component overrides needed.
 *
 * "sm" = 14px  → ~87.5% of default; fits more desktop features on mobile.
 * "md" = 16px  → browser default.
 * "lg" = 18px  → ~112.5% larger for accessibility / small text needs.
 */
const STORAGE_KEY = "mercarie-global_fontsize";
const PX_BY_SIZE = { sm: 14, md: 16, lg: 18 };

const FontSizeContext = createContext({ size: "md", setSize: () => {} });

export const FontSizeProvider = ({ children }) => {
  const [size, setSizeState] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved && PX_BY_SIZE[saved] ? saved : "md";
    } catch {
      return "md";
    }
  });

  useEffect(() => {
    const px = PX_BY_SIZE[size] || 16;
    document.documentElement.style.fontSize = `${px}px`;
    try { localStorage.setItem(STORAGE_KEY, size); } catch { /* private mode */ }
  }, [size]);

  const setSize = useCallback((next) => {
    if (PX_BY_SIZE[next]) setSizeState(next);
  }, []);

  return (
    <FontSizeContext.Provider value={{ size, setSize }}>
      {children}
    </FontSizeContext.Provider>
  );
};

export const useFontSize = () => useContext(FontSizeContext);
