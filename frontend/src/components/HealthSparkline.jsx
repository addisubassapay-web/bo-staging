import React, { useMemo } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

const tierColor = {
  excellent: "#10b981",  // emerald-500
  good:      "#3b82f6",  // blue-500
  at_risk:   "#f59e0b",  // amber-500
  poor:      "#ef4444",  // red-500
  no_data:   "#d4d4d4",  // neutral-300
};

/**
 * HealthSparkline — inline SVG line chart over the last N days.
 * `data` is an array of {date, score, tier}. Nulls (no_data days) are
 * drawn as gaps. Colour-coded by the tier of the most recent point.
 */
const HealthSparkline = ({ data = [], height = 44, width = 240 }) => {
  const { points, trend, lineColor, avg, latest, minS, maxS } = useMemo(() => {
    const filled = data.filter((d) => d && d.score !== null && d.score !== undefined);
    if (filled.length === 0) {
      return { points: "", trend: "flat", lineColor: tierColor.no_data, avg: null, latest: null, minS: 0, maxS: 100 };
    }
    const scores = filled.map((d) => d.score);
    const min = 0;    // fixed y-axis to make cross-time-period comparisons meaningful
    const max = 100;
    const stepX = data.length > 1 ? width / (data.length - 1) : 0;
    // Build SVG polyline points — leave holes for null days by breaking segments.
    // (For simplicity we skip gaps: just connect the filled points spaced by data index.)
    const pts = data
      .map((d, i) => {
        if (!d || d.score === null || d.score === undefined) return null;
        const x = i * stepX;
        const y = height - ((d.score - min) / (max - min)) * (height - 4) - 2;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .filter(Boolean)
      .join(" ");
    const first = scores[0];
    const last = scores[scores.length - 1];
    const delta = last - first;
    const trend = Math.abs(delta) < 3 ? "flat" : delta > 0 ? "up" : "down";
    const lastTier = filled[filled.length - 1]?.tier || "no_data";
    return {
      points: pts,
      trend,
      lineColor: tierColor[lastTier] || tierColor.no_data,
      avg: Math.round(scores.reduce((a, b) => a + b, 0) / scores.length),
      latest: last,
      minS: Math.min(...scores),
      maxS: Math.max(...scores),
    };
  }, [data, height, width]);

  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
  const trendColor = trend === "up" ? "text-emerald-600" : trend === "down" ? "text-red-600" : "text-neutral-400";

  return (
    <div className="flex items-center gap-3" data-testid="health-sparkline">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="flex-shrink-0"
        aria-label="Health score trend"
      >
        {/* baseline grid at 50 and 80 */}
        <line x1="0" x2={width} y1={height - (50 / 100) * (height - 4) - 2} y2={height - (50 / 100) * (height - 4) - 2} stroke="#e5e5e5" strokeDasharray="2 3" />
        <line x1="0" x2={width} y1={height - (80 / 100) * (height - 4) - 2} y2={height - (80 / 100) * (height - 4) - 2} stroke="#e5e5e5" strokeDasharray="2 3" />
        {points && (
          <polyline
            points={points}
            fill="none"
            stroke={lineColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {/* latest point dot */}
        {points && data.length > 0 && (() => {
          const filled = data.filter((d) => d && d.score !== null && d.score !== undefined);
          const lastPt = filled[filled.length - 1];
          const lastIdx = data.lastIndexOf(lastPt);
          const stepX = data.length > 1 ? width / (data.length - 1) : 0;
          const cx = lastIdx * stepX;
          const cy = height - ((lastPt.score - 0) / 100) * (height - 4) - 2;
          return <circle cx={cx} cy={cy} r="3" fill={lineColor} />;
        })()}
      </svg>
      <div className="text-xs">
        <div className="flex items-center gap-1 font-semibold text-neutral-900">
          <TrendIcon className={`w-3.5 h-3.5 ${trendColor}`} />
          <span>{latest !== null ? Math.round(latest) : "—"}</span>
          <span className={`text-[10px] ${trendColor}`}>
            {trend === "up" && "improving"}
            {trend === "down" && "declining"}
            {trend === "flat" && "steady"}
          </span>
        </div>
        <div className="text-[10px] text-neutral-500 mt-0.5">
          30d · min {minS ?? "—"} · avg {avg ?? "—"} · max {maxS ?? "—"}
        </div>
      </div>
    </div>
  );
};

export default HealthSparkline;
