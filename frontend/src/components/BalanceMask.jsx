import React from "react";
import { Eye, EyeOff } from "lucide-react";

/**
 * useBalanceVisibility — persist the "eye" state per-device in localStorage
 * so hiding your balance carries across page loads.
 */
export function useBalanceVisibility(key = "merchari-global_balance_visible") {
  const [visible, setVisible] = React.useState(() => {
    try {
      const v = localStorage.getItem(key);
      return v === null ? true : v === "1";
    } catch { return true; }
  });
  const toggle = React.useCallback(() => {
    setVisible((v) => {
      const next = !v;
      try { localStorage.setItem(key, next ? "1" : "0"); } catch {}
      return next;
    });
  }, [key]);
  return [visible, toggle];
}

/**
 * BalanceValue — renders a monetary value that respects the global
 * balance-visibility toggle. When hidden, shows "••••••" of similar width.
 */
export const BalanceValue = ({ value, visible, className = "", testId }) => (
  <span className={`tabular-nums ${className}`} data-testid={testId} aria-live="polite">
    {visible
      ? (typeof value === "string" ? value : `$${Number(value || 0).toFixed(2)}`)
      : "••••••"}
  </span>
);

/**
 * BalanceEyeToggle — a small icon-button that flips the visibility state.
 */
export const BalanceEyeToggle = ({ visible, onToggle, size = 4, className = "", testId = "balance-toggle" }) => (
  <button
    type="button"
    onClick={onToggle}
    aria-label={visible ? "Hide balance" : "Show balance"}
    aria-pressed={visible}
    title={visible ? "Hide balance" : "Show balance"}
    className={`inline-flex items-center justify-center h-8 w-8 rounded-full text-white/80 hover:text-white hover:bg-white/10 focus:outline-none focus:bg-white/10 transition ${className}`}
    data-testid={testId}
  >
    {visible
      ? <Eye className={`h-${size} w-${size}`} />
      : <EyeOff className={`h-${size} w-${size}`} />}
  </button>
);
