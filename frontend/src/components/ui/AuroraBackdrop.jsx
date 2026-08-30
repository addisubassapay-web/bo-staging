import React from "react";

/**
 * AuroraBackdrop — fixed-position decorative gradient blobs that live
 * behind page content. Adds depth + brand-coloured ambient light without
 * heavy imagery. Two variants:
 *
 *   • "indigo" (default) — cool, marketplace hero look
 *   • "warm"             — mixes indigo + red accent for CTA-heavy pages
 *
 * All blobs are absolutely positioned with pointer-events-none so they
 * never block clicks. Wrap them in a `relative` parent (or use the
 * default `fixed` positioning) to layer content on top.
 */
export const AuroraBackdrop = ({
  variant = "indigo",
  fixed = false,
  className = "",
  "data-testid": testId = "aurora-backdrop",
}) => {
  const wrapper = fixed
    ? "fixed inset-0 -z-10 pointer-events-none overflow-hidden"
    : `absolute inset-0 -z-0 pointer-events-none overflow-hidden ${className}`;

  const blobs = variant === "warm"
    ? [
        { pos: "-top-32 -left-32", size: "h-[26rem] w-[26rem]", color: "bg-[#5459E8]", opacity: "opacity-30" },
        { pos: "-bottom-40 -right-20", size: "h-[28rem] w-[28rem]", color: "bg-[#FF0515]", opacity: "opacity-20" },
        { pos: "top-1/3 left-1/2", size: "h-64 w-64", color: "bg-[#818CF8]", opacity: "opacity-25" },
      ]
    : [
        { pos: "-top-40 -left-20", size: "h-[28rem] w-[28rem]", color: "bg-[#5459E8]", opacity: "opacity-25" },
        { pos: "-bottom-32 -right-32", size: "h-[26rem] w-[26rem]", color: "bg-[#818CF8]", opacity: "opacity-30" },
        { pos: "top-1/2 right-1/4", size: "h-56 w-56", color: "bg-[#F0ABFC]", opacity: "opacity-15" },
      ];

  return (
    <div className={wrapper} aria-hidden data-testid={testId}>
      {blobs.map((b, i) => (
        <div
          key={i}
          className={`absolute rounded-full blur-[110px] ${b.pos} ${b.size} ${b.color} ${b.opacity} animate-aurora-drift`}
          style={{ animationDelay: `${i * 2.4}s` }}
        />
      ))}
      {/* Fine grain overlay adds subtle texture that keeps big gradients from feeling flat */}
      <div
        className="absolute inset-0 opacity-[0.035] mix-blend-overlay"
        style={{
          backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")`,
        }}
      />
    </div>
  );
};

export default AuroraBackdrop;
