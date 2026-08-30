import React from "react";

/**
 * WaveDivider — full-width SVG wave transition between page sections.
 * Reinforces the BlueOcean wave motif from the logo and turns hard
 * section breaks into playful transitions. Can flip vertically to
 * cap the top or bottom of a coloured band.
 *
 * Props:
 *  - flip: boolean — mirror the wave upside-down (useful for section tops)
 *  - fill: css color (default indigo brand primary)
 *  - height: css height (default "h-16 sm:h-20")
 */
export const WaveDivider = ({
  flip = false,
  fill = "#5459E8",
  height = "h-16 sm:h-20",
  className = "",
  "data-testid": testId = "wave-divider",
}) => (
  <div
    className={`w-full ${height} overflow-hidden pointer-events-none ${className}`}
    aria-hidden
    data-testid={testId}
    style={{ transform: flip ? "scaleY(-1)" : "none" }}
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1440 96"
      preserveAspectRatio="none"
      className="w-full h-full"
    >
      <defs>
        <linearGradient id="wd-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={fill} stopOpacity="0.15" />
          <stop offset="50%" stopColor={fill} stopOpacity="0.35" />
          <stop offset="100%" stopColor={fill} stopOpacity="0.15" />
        </linearGradient>
      </defs>
      <path
        d="M0,48 C240,96 480,0 720,32 C960,64 1200,16 1440,48 L1440,96 L0,96 Z"
        fill="url(#wd-gradient)"
      />
      <path
        d="M0,64 C240,32 480,96 720,64 C960,32 1200,80 1440,56 L1440,96 L0,96 Z"
        fill={fill}
        fillOpacity="0.18"
      />
    </svg>
  </div>
);

export default WaveDivider;
