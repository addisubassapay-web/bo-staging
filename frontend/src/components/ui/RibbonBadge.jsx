import React from "react";

/**
 * RibbonBadge — diagonal corner ribbon that stamps a card with a
 * marketing tag ("HOT", "TRENDING", "NEW", "SALE"). Fully SVG-based
 * so it scales cleanly and inherits parent border-radius through
 * overflow-hidden on the ancestor.
 *
 * Drop it inside a `relative overflow-hidden` container (e.g. a
 * ProductCard or hero slide) and it will anchor to the top-right
 * corner by default.
 *
 * Props:
 *  - variant: "hot" | "trending" | "new" | "sale" | "flash"
 *  - side: "right" | "left" (default "right")
 *  - size: "sm" | "md" (default "md")
 *  - label: string — override default label
 */
const VARIANT_MAP = {
  hot:      { grad: ["#FF0515", "#FF5B6B"], label: "HOT" },
  trending: { grad: ["#5459E8", "#818CF8"], label: "TRENDING" },
  new:      { grad: ["#16A34A", "#22C55E"], label: "NEW" },
  sale:     { grad: ["#DC2626", "#F97316"], label: "SALE" },
  flash:    { grad: ["#F0ABFC", "#F472B6"], label: "FLASH" },
};

export const RibbonBadge = ({
  variant = "hot",
  side = "right",
  size = "md",
  label,
  className = "",
  "data-testid": testId = "ribbon-badge",
}) => {
  const cfg = VARIANT_MAP[variant] || VARIANT_MAP.hot;
  const uid = React.useId();
  const gradId = `rb-grad-${uid}`;
  const dim = size === "sm" ? 80 : 110;
  const flip = side === "left" ? "scale-x-[-1]" : "";

  return (
    <div
      className={`absolute top-0 right-0 pointer-events-none ${flip} ${className}`}
      aria-hidden
      data-testid={testId}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={dim}
        height={dim}
        viewBox="0 0 110 110"
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={cfg.grad[0]} />
            <stop offset="100%" stopColor={cfg.grad[1]} />
          </linearGradient>
        </defs>
        {/* Cast shadow tucked under the ribbon */}
        <path d="M110,32 L82,4 L60,26 L88,54 Z" fill="rgba(0,0,0,0.18)" />
        {/* The ribbon flag */}
        <path
          d="M110,0 L110,32 L78,64 L46,32 L78,0 Z"
          fill={`url(#${gradId})`}
        />
        {/* Diagonal text baseline */}
        <text
          x="78"
          y="32"
          fill="#ffffff"
          fontFamily="Poppins, DM Sans, sans-serif"
          fontWeight="800"
          fontSize={size === "sm" ? 12 : 13}
          textAnchor="middle"
          transform="rotate(-45 78 32)"
          style={{ letterSpacing: "0.06em" }}
        >
          {(label || cfg.label).toUpperCase()}
        </text>
      </svg>
    </div>
  );
};

export default RibbonBadge;
