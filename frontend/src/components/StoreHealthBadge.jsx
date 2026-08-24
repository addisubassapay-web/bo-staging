import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Zap, ShieldCheck } from "lucide-react";

/**
 * StoreHealthBadge — public "Ships fast" / "Reliable seller" chip shown
 * on the store page header. Fed by GET /stores/:slug/health-badge which
 * only returns positive tiers (excellent/good). Silently renders nothing
 * otherwise, so unhealthy sellers aren't publicly shamed.
 */
const StoreHealthBadge = ({ slug }) => {
  const [badge, setBadge] = useState(null);

  useEffect(() => {
    if (!slug) return;
    api
      .get(`/stores/${slug}/health-badge`)
      .then((r) => setBadge(r.data))
      .catch(() => setBadge(null));
  }, [slug]);

  if (!badge?.visible) return null;
  const tier = badge.tier;
  const Icon = tier === "excellent" ? Zap : ShieldCheck;
  const palette =
    tier === "excellent"
      ? "bg-emerald-50 border-emerald-200 text-emerald-800"
      : "bg-blue-50 border-blue-200 text-blue-800";

  return (
    <span
      data-testid="store-health-badge"
      title={`Score: ${badge.score}/100 (rolling 30 days)`}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border text-[11px] font-semibold ${palette}`}
    >
      <Icon className="w-3 h-3" />
      {badge.label}
    </span>
  );
};

export default StoreHealthBadge;
