import React from "react";

/**
 * BrandMark — reusable inline SVG brand logo for BlueOcean.
 *
 * Design: a geometric shopping-bag silhouette carrying a stylised wave —
 * fusing e-commerce (bag + tag dot) with the "Ocean" motion motif. Sits on
 * a rounded-square tile filled with the indigo brand gradient (#5459E8 →
 * #818CF8). The wave crest cuts through the bag from left to right, so
 * "commerce + flow" reads at any size from favicon to hero.
 *
 * Props:
 *  - size: number | string (px or CSS size, default 40)
 *  - variant: "default" | "mono" | "outline"
 *      • default → indigo tile, white bag + wave, indigo accent dot
 *      • mono    → transparent tile, white outlines (dark backdrops)
 *      • outline → transparent tile, indigo outlines (light stamps)
 *  - showWordmark: boolean — renders "Blue" + coloured "Ocean" wordmark
 *  - wordmarkClassName / className: extra classes
 *  - animated: boolean — subtle pulse on mount
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
  const dotGrad = `bm-dot-${uid}`;

  const isOutline = variant === "outline";
  const isMono = variant === "mono";
  const isDefault = variant === "default";

  const tileFill = isDefault ? `url(#${tileGrad})` : "none";
  const tileStroke = isOutline ? "#5459E8" : "none";
  const strokeColor = isMono ? "#ffffff" : isOutline ? "#5459E8" : "#ffffff";
  const dotFill = isMono ? "#ffffff" : isOutline ? "#5459E8" : `url(#${dotGrad})`;

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
            <stop offset="0%" stopColor="#5459E8" />
            <stop offset="100%" stopColor="#818CF8" />
          </linearGradient>
          <linearGradient id={dotGrad} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F0ABFC" />
            <stop offset="100%" stopColor="#F472B6" />
          </linearGradient>
        </defs>

        {/* Rounded tile — the brand container */}
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

        {/* Shopping bag body — geometric trapezoid with a subtle taper */}
        <path
          d="M36 50 L84 50 L88 96 Q88 100 84 100 L36 100 Q32 100 32 96 Z"
          fill="none"
          stroke={strokeColor}
          strokeWidth="6"
          strokeLinejoin="round"
        />

        {/* Bag handles — twin arches sitting on the bag top edge */}
        <path
          d="M46 50 L46 40 Q46 30 54 30 Q62 30 62 40 L62 50"
          fill="none"
          stroke={strokeColor}
          strokeWidth="5"
          strokeLinecap="round"
        />
        <path
          d="M58 50 L58 40 Q58 30 66 30 Q74 30 74 40 L74 50"
          fill="none"
          stroke={strokeColor}
          strokeWidth="5"
          strokeLinecap="round"
          opacity="0.85"
        />

        {/* Signature wave crest running through the bag — "ocean flow" */}
        <path
          d="M34 78 Q46 70 58 78 T82 78"
          fill="none"
          stroke={strokeColor}
          strokeWidth="5"
          strokeLinecap="round"
        />
        <path
          d="M34 90 Q46 82 58 90 T82 90"
          fill="none"
          stroke={strokeColor}
          strokeWidth="5"
          strokeLinecap="round"
          opacity="0.55"
        />

        {/* Accent price-tag dot — top-right geometric flourish */}
        <circle
          cx="92"
          cy="28"
          r="11"
          fill={dotFill}
          stroke={isMono ? "rgba(255,255,255,0.7)" : "#ffffff"}
          strokeWidth="3"
        />
      </svg>

      {showWordmark && (
        <span
          className={`font-bold tracking-tight ${wordmarkClassName}`}
          style={{ fontSize: typeof size === "number" ? size * 0.5 : "1rem" }}
        >
          Blue<span style={{ color: "#5459E8" }}>Ocean</span>
        </span>
      )}
    </span>
  );
};

export default BrandMark;
