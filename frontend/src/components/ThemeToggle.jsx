import React from "react";
import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

/**
 * ThemeToggle — day/night button. Extracted from Header.jsx so it can be
 * imported by the settings-menu popover without pulling the whole Header
 * module.
 */
const ThemeToggle = () => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 hover:border-[#1E40AF] grid place-items-center transition-colors relative overflow-hidden dark:border-neutral-700 dark:hover:border-[#1E40AF]"
      data-testid="theme-toggle"
    >
      <Sun className={`h-5 w-5 text-neutral-700 absolute transition-all duration-300 ${isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"}`} />
      <Moon className={`h-5 w-5 text-[#1E40AF] absolute transition-all duration-300 ${isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"}`} />
    </button>
  );
};

export default ThemeToggle;
