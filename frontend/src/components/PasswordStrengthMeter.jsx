import React, { useMemo } from "react";
import { Check, X } from "lucide-react";

/**
 * PasswordStrengthMeter — pure, dependency-free strength scoring.
 *
 * Scores 0-4 based on:
 *   - length ≥ 8 (+1)  ·  length ≥ 12 (+1)
 *   - has lowercase
 *   - has uppercase
 *   - has digit
 *   - has symbol
 *   - not in a small deny-list of very common patterns
 *
 * We deliberately keep this simple (no zxcvbn dep) so bundle size stays small.
 */
const DENY = new Set([
  "password", "12345678", "welcome-2026", "welcome2026",
  "qwerty", "letmein", "iloveyou", "admin123", "password1",
]);

function score(pwd) {
  if (!pwd) return { level: 0, checks: {}, tips: [] };
  const p = pwd;
  const checks = {
    length8: p.length >= 8,
    length12: p.length >= 12,
    lower: /[a-z]/.test(p),
    upper: /[A-Z]/.test(p),
    digit: /\d/.test(p),
    symbol: /[^A-Za-z0-9]/.test(p),
    notCommon: !DENY.has(p.toLowerCase()),
  };
  let raw = 0;
  if (checks.length8) raw += 1;
  if (checks.length12) raw += 1;
  if (checks.lower && checks.upper) raw += 1;
  if (checks.digit) raw += 1;
  if (checks.symbol) raw += 1;
  if (!checks.notCommon) raw = Math.min(raw, 1);
  // Map raw 0..5 → level 0..4
  const level = Math.max(0, Math.min(4, raw - 1));
  const tips = [];
  if (!checks.length8) tips.push("Use at least 8 characters");
  else if (!checks.length12) tips.push("12+ characters is stronger");
  if (!(checks.lower && checks.upper)) tips.push("Mix upper & lower case");
  if (!checks.digit) tips.push("Add a number");
  if (!checks.symbol) tips.push("Add a symbol (!, @, #, ...)");
  if (!checks.notCommon) tips.push("Avoid common passwords");
  return { level, checks, tips };
}

const LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"];
const COLORS = [
  "bg-neutral-300",
  "bg-red-500",
  "bg-amber-500",
  "bg-lime-500",
  "bg-emerald-600",
];
const TEXT = [
  "text-neutral-500",
  "text-red-600",
  "text-amber-600",
  "text-lime-700",
  "text-emerald-700",
];

const PasswordStrengthMeter = ({ password = "" }) => {
  const { level, tips } = useMemo(() => score(password), [password]);
  const segments = [0, 1, 2, 3];
  return (
    <div className="mt-2" data-testid="pwd-strength-meter">
      <div className="flex gap-1">
        {segments.map((i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < level ? COLORS[level] : "bg-neutral-200 dark:bg-neutral-700"
            }`}
            data-testid={`pwd-strength-seg-${i}`}
          />
        ))}
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span
          className={`text-xs font-medium ${TEXT[level]}`}
          data-testid="pwd-strength-label"
        >
          {password ? LABELS[level] : "Type a password"}
        </span>
        {password && level >= 3 && (
          <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
            <Check className="h-3 w-3" /> Nice and solid
          </span>
        )}
      </div>
      {password && tips.length > 0 && (
        <ul className="mt-2 space-y-0.5" data-testid="pwd-strength-tips">
          {tips.map((t, i) => (
            <li
              key={i}
              className="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400"
            >
              <X className="h-3 w-3 text-neutral-400" />
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default PasswordStrengthMeter;
export { score as scorePassword };
