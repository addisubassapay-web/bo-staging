import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Activity, TrendingUp, Timer, PackageCheck, ShieldAlert, Loader2 } from "lucide-react";

const tierPalette = {
  excellent: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", label: "Excellent" },
  good:      { bg: "bg-blue-50",    border: "border-blue-200",    text: "text-blue-700",    label: "Good" },
  at_risk:   { bg: "bg-amber-50",   border: "border-amber-200",   text: "text-amber-800",   label: "At risk" },
  poor:      { bg: "bg-red-50",     border: "border-red-200",     text: "text-red-700",     label: "Poor" },
  no_data:   { bg: "bg-neutral-50", border: "border-neutral-200", text: "text-neutral-500", label: "No data yet" },
};

const StoreHealthCard = () => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/seller/store-health", { params: { days: 30 } })
      .then((r) => setHealth(r.data))
      .catch(() => setHealth(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-4 flex items-center gap-2 text-sm text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading store health…
      </div>
    );
  }

  if (!health) return null;
  const palette = tierPalette[health.tier] || tierPalette.no_data;
  const fmtPct = (n) => (n === null || n === undefined ? "—" : `${n}%`);
  const fmtHours = (n) => (n === null || n === undefined ? "—" : `${n}h`);

  return (
    <div
      data-testid="store-health-card"
      className={`rounded-xl border ${palette.border} ${palette.bg} p-4 sm:p-5 space-y-4`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
            <Activity className="w-3.5 h-3.5" /> Store health · last {health.window_days} days
          </div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="text-3xl font-bold text-neutral-900" data-testid="store-health-score">
              {health.score === null ? "—" : health.score}
            </span>
            <span className={`text-sm font-semibold ${palette.text}`} data-testid="store-health-tier">
              {palette.label}
            </span>
          </div>
        </div>
        <div className="text-xs text-neutral-600 max-w-xs text-right">
          Faster pickups and higher acceptance = higher trust, more visibility, and fewer auto-cancels.
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg bg-white/70 border border-neutral-200 p-3">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
            <PackageCheck className="w-3 h-3" /> Acceptance rate
          </div>
          <div className="text-2xl font-bold text-neutral-900 mt-1" data-testid="store-health-acceptance">
            {fmtPct(health.acceptance_rate_pct)}
          </div>
          <div className="text-[11px] text-neutral-500 mt-0.5">
            {health.picked_count}/{health.total_orders} orders picked
          </div>
        </div>
        <div className="rounded-lg bg-white/70 border border-neutral-200 p-3">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
            <TrendingUp className="w-3 h-3" /> On-time rate
          </div>
          <div className="text-2xl font-bold text-neutral-900 mt-1" data-testid="store-health-ontime">
            {fmtPct(health.on_time_rate_pct)}
          </div>
          <div className="text-[11px] text-neutral-500 mt-0.5">
            Picked before deadline expired
          </div>
        </div>
        <div className="rounded-lg bg-white/70 border border-neutral-200 p-3">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
            <Timer className="w-3 h-3" /> Avg. response time
          </div>
          <div className="text-2xl font-bold text-neutral-900 mt-1" data-testid="store-health-response">
            {fmtHours(health.avg_response_hours)}
          </div>
          <div className="text-[11px] text-neutral-500 mt-0.5">
            From order placed → picked
          </div>
        </div>
      </div>

      {health.auto_cancelled_count > 0 && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-800 flex items-center gap-2" data-testid="store-health-cancel-warning">
          <ShieldAlert className="w-3.5 h-3.5 flex-shrink-0" />
          {health.auto_cancelled_count} order{health.auto_cancelled_count === 1 ? "" : "s"} auto-cancelled in this window — those hurt your score the most.
        </div>
      )}
    </div>
  );
};

export default StoreHealthCard;
