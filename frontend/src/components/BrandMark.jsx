import React from "react";

/**
 * BrandMark — reusable inline SVG brand logo for BlueOcean.
 *
 * The mark is a stylised wave/ocean-drop composed of two overlapping arcs
 * inside a rounded-square container. It reads as "water + motion" on the
 * marketplace's blue palette (#1E40AF primary, #3B82F6 secondary).
 *
 * Props:
 *  - size: number | string (px or CSS size, default 40)
 *  - variant: "default" | "mono" | "outline" (default "default")
 *      • default → blue gradient tile with white waves
 *      • mono    → transparent tile + white waves (for dark hero backdrops)
 *      • outline → transparent tile + blue-stroked waves (for footers/stamps)
 *  - showWordmark: boolean (default false) — renders the "BlueOcean" wordmark
 *  - wordmarkClassName: extra classes for the wordmark
 *  - className: extra classes on the wrapper
 *  - animated: boolean — adds a subtle draw/pulse on mount
 *  - "data-testid": string
 */
export const BrandMark = ({
  size = 40,
  variant = "default",
  showWordmark = false,
  wordmarkClassName = "",
  className = "",
  animated = false,
  ...rest
}) => {
  const uid = React.useId();
  const tileGrad = `bm-tile-${uid}`;
  const waveGrad = `bm-wave-${uid}`;

  const isOutline = variant === "outline";
  const isMono = variant === "mono";

  const tileFill = isOutline || isMono ? "none" : `url(#${tileGrad})`;
  const tileStroke = isOutline ? "#1E40AF" : "none";
  const waveStroke = isMono ? "#ffffff" : isOutline ? "#1E40AF" : "#ffffff";
  const dropFill = isMono ? "#ffffff" : isOutline ? "#1E40AF" : `url(#${waveGrad})`;

  return (
    <span
      className={`inline-flex items-center gap-2 ${className}`}
      {...rest}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 120 120"
        width={size}
        height={size}
        role="img"
        aria-label="BlueOcean"
        className={`shrink-0 ${animated ? "brand-mark-animated" : ""} drop-shadow-sm`}
      >
        <defs>
          <linearGradient id={tileGrad} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#1E40AF" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id={waveGrad} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#DBEAFE" />
          </linearGradient>
        </defs>

        {/* Rounded-square tile — the brand container */}
        <rect
          x="6"
          y="6"
          width="108"
          height="108"
          rx="26"
          ry="26"
          fill={tileFill}
          stroke={tileStroke}
          strokeWidth={isOutline ? 6 : 0}
        />

        {/* Water drop — top accent */}
        <path
          d="M60 22 C 52 34, 46 42, 46 52 C 46 60, 52 66, 60 66 C 68 66, 74 60, 74 52 C 74 42, 68 34, 60 22 Z"
          fill={dropFill}
          opacity={isOutline ? 1 : 0.95}
        />

        {/* Two stacked wave crests below the drop */}
        <path
          d="M20 82 C 32 72, 44 92, 60 82 C 76 72, 88 92, 100 82"
          fill="none"
          stroke={waveStroke}
          strokeWidth="7"
          strokeLinecap="round"
        />
        <path
          d="M20 98 C 32 88, 44 108, 60 98 C 76 88, 88 108, 100 98"
          fill="none"
          stroke={waveStroke}
          strokeWidth="7"
          strokeLinecap="round"
          opacity="0.7"
        />
      </svg>

      {showWordmark && (
        <span
          className={`font-bold tracking-tight ${wordmarkClassName}`}
          style={{ fontSize: typeof size === "number" ? size * 0.5 : "1rem" }}
        >
          Blue<span style={{ color: "#1E40AF" }}>Ocean</span>
        </span>
      )}
    </span>
  );
};

export default BrandMark;
