import React from "react";

/**
 * BrandMark — reusable inline SVG brand logo.
 *
 * Props:
 *  - size: number | string (px or CSS size, default 40)
 *  - variant: "default" | "mono" | "outline" (default "default")
 *      • default → orange→red gradient hex + white M + amber orb
 *      • mono    → white hex outline + white M (for dark hero backdrops)
 *      • outline → transparent fill + orange stroke (for footers / stamps)
 *  - showWordmark: boolean (default false) — renders "mercari" text next to the mark
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
  const hexGrad = `bm-hex-${uid}`;
  const dotGrad = `bm-dot-${uid}`;

  // Palette per variant
  const hexFill = variant === "outline" ? "none" : `url(#${hexGrad})`;
  const hexStroke = variant === "outline" ? "#FF5722" : `url(#${hexGrad})`;
  const mStroke = variant === "outline" ? "#FF5722" : "#ffffff";
  const showDot = variant !== "outline";

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
        aria-label="Mercari"
        className={`shrink-0 ${animated ? "brand-mark-animated" : ""} drop-shadow-sm`}
      >
        <defs>
          <linearGradient id={hexGrad} x1="0%" y1="0%" x2="100%" y2="100%">
            {variant === "mono" ? (
              <>
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
                <stop offset="100%" stopColor="#ffffff" stopOpacity="0.7" />
              </>
            ) : (
              <>
                <stop offset="0%" stopColor="#FF7A18" />
                <stop offset="100%" stopColor="#FF211F" />
              </>
            )}
          </linearGradient>
          <linearGradient id={dotGrad} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FDE68A" />
            <stop offset="100%" stopColor="#F59E0B" />
          </linearGradient>
        </defs>

        {/* Rounded pointy-top hex */}
        <polygon
          points="60,10 103,35 103,85 60,110 17,85 17,35"
          fill={hexFill}
          stroke={hexStroke}
          strokeWidth={variant === "outline" ? 8 : 14}
          strokeLinejoin="round"
        />

        {/* Custom uppercase M with V-middle */}
        <path
          d="M35,82 L35,40 L60,66 L85,40 L85,82"
          fill="none"
          stroke={mStroke}
          strokeWidth="9.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Amber accent orb (bottom-right) */}
        {showDot && (
          <>
            <circle cx="94" cy="94" r="15" fill={`url(#${dotGrad})`} />
            <circle
              cx="94"
              cy="94"
              r="15"
              fill="none"
              stroke={variant === "mono" ? "rgba(255,255,255,0.7)" : "#ffffff"}
              strokeWidth="3"
              opacity="0.95"
            />
          </>
        )}
      </svg>

      {showWordmark && (
        <span
          className={`font-bold tracking-tight ${wordmarkClassName}`}
          style={{ fontSize: typeof size === "number" ? size * 0.5 : "1rem" }}
        >
          mercari
        </span>
      )}
    </span>
  );
};

export default BrandMark;
