import React from "react";

/**
 * StickerChip — a slightly rotated, gradient-filled chip that reads as
 * a promotional sticker slapped onto a card. Great for time-sensitive
 * cues ("24H LEFT", "-40%", "FREE SHIPPING") — an eye-catching upgrade
 * from the usual outline pill.
 *
 * Props:
 *  - tone: "red" | "indigo" | "success" | "warn" | "candy" (default "red")
 *  - size: "sm" | "md"                                     (default "sm")
 *  - tilt: number in degrees (default -6)
 *  - pulse: boolean — apply a subtle 2s heartbeat
 *  - children: sticker content
 */
const TONE_MAP = {
  red:     { from: "#FF0515", to: "#FF5B6B", ink: "#ffffff" },
  indigo:  { from: "#5459E8", to: "#818CF8", ink: "#ffffff" },
  success: { from: "#16A34A", to: "#22C55E", ink: "#ffffff" },
  warn:    { from: "#F59E0B", to: "#FBBF24", ink: "#111827" },
  candy:   { from: "#F0ABFC", to: "#F472B6", ink: "#111827" },
};

export const StickerChip = ({
  tone = "red",
  size = "sm",
  tilt = -6,
  pulse = false,
  className = "",
  children,
  "data-testid": testId = "sticker-chip",
}) => {
  const cfg = TONE_MAP[tone] || TONE_MAP.red;
  const pad = size === "md" ? "px-4 py-1.5 text-xs" : "px-3 py-1 text-[10.5px]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-extrabold uppercase tracking-wider rounded-md shadow-lg ring-1 ring-black/5 ${pad} ${pulse ? "sticker-pulse" : ""} ${className}`}
      style={{
        background: `linear-gradient(135deg, ${cfg.from} 0%, ${cfg.to} 100%)`,
        color: cfg.ink,
        transform: `rotate(${tilt}deg)`,
      }}
      data-testid={testId}
    >
      {children}
    </span>
  );
};

export default StickerChip;
