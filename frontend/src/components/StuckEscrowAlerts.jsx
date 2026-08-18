import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Link } from "react-router-dom";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Bell, MessageCircle, ChevronDown, ChevronUp } from "lucide-react";

/**
 * Wallet section that surfaces every seller order whose funds are still
 * frozen past the delivery ETA. This is the in-app companion to the
 * weekly Escrow Alerts Digest email — sellers can see the same list and
 * one-click "Nudge buyer" (opens the buyer thread) to unlock funds.
 */
const StuckEscrowAlerts = () => {
  const { format } = useCurrency();
  const { t } = useLang();
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [nudging, setNudging] = useState({});

  useEffect(() => {
    let cancelled = false;
    api.get("/wallet/escrow-alerts", { params: { threshold_days: 0 } })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setData({ stuck: [], total_frozen: 0 }); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading || !data || !data.stuck || data.stuck.length === 0) return null;

  const stuck = data.stuck;
  const total = data.total_frozen;
  const visible = expanded ? stuck : stuck.slice(0, 3);
  const remaining = stuck.length - visible.length;

  const nudge = async (order) => {
    setNudging((s) => ({ ...s, [order.order_id]: true }));
    try {
      await api.post(`/orders/${order.order_id}/nudge-buyer`, {});
      toast({
        title: t("escrow.nudgeSent") || "Nudge sent",
        description: (t("escrow.nudgeDesc") || "We reminded {buyer} to confirm delivery.").replace("{buyer}", order.buyer_name || "the buyer"),
      });
    } catch (e) {
      toast({
        title: t("escrow.nudgeFail") || "Couldn't send nudge",
        description: e?.response?.data?.detail || (t("escrow.tryAgain") || "Try again"),
        variant: "destructive",
      });
    } finally {
      setNudging((s) => ({ ...s, [order.order_id]: false }));
    }
  };

  return (
    <div
      className="rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50/50 p-5 sm:p-6 mb-8"
      data-testid="stuck-escrow-alerts"
    >
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 text-white grid place-items-center shrink-0">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-amber-900">
              {(t("escrow.title") || "{n} order(s) stuck in escrow").replace("{n}", String(stuck.length))}
            </div>
            <div className="text-xs text-amber-800/80">
              {(t("escrow.subtitle") || "{amount} awaiting release · nudge buyers to unlock funds")
                .replace("{amount}", format(total))}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {visible.map((s) => (
          <div
            key={s.order_id}
            className="flex items-center gap-3 rounded-xl bg-white border border-amber-100 p-3"
            data-testid={`escrow-alert-${s.order_id}`}
          >
            {s.listing_image ? (
              <img src={s.listing_image} alt="" className="h-11 w-11 rounded-lg object-cover shrink-0" loading="lazy" />
            ) : (
              <div className="h-11 w-11 rounded-lg bg-amber-100 grid place-items-center shrink-0">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-neutral-900 line-clamp-1">{s.listing_title}</div>
              <div className="text-[11px] text-neutral-500 flex items-center gap-1.5 flex-wrap">
                <span>{t("escrow.buyer") || "Buyer"}: {s.buyer_name || "—"}</span>
                <span>·</span>
                <span className="text-amber-700 font-semibold">
                  {(t("escrow.overdue") || "{n} day(s) overdue").replace("{n}", String(s.overdue_days))}
                </span>
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-bold tabular-nums text-emerald-600">{format(s.amount)}</div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => nudge(s)}
                disabled={!!nudging[s.order_id]}
                className="mt-1 h-8 border-amber-300 text-amber-800 hover:bg-amber-100 hover:text-amber-900"
                data-testid={`nudge-buyer-${s.order_id}`}
              >
                <Bell className="h-3 w-3 mr-1" />
                {nudging[s.order_id] ? (t("escrow.nudging") || "Nudging…") : (t("escrow.nudge") || "Nudge")}
              </Button>
            </div>
          </div>
        ))}
      </div>

      {stuck.length > 3 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-amber-800 hover:text-amber-900"
          data-testid="escrow-alerts-toggle"
        >
          {expanded ? (
            <>{t("escrow.showLess") || "Show less"} <ChevronUp className="h-3 w-3" /></>
          ) : (
            <>{(t("escrow.showMore") || "Show {n} more").replace("{n}", String(remaining))} <ChevronDown className="h-3 w-3" /></>
          )}
        </button>
      )}

      <div className="mt-4 flex items-center justify-between text-[11px] text-amber-900/70 flex-wrap gap-2">
        <div className="inline-flex items-center gap-1">
          <MessageCircle className="h-3 w-3" />
          {t("escrow.helper") || "You'll also get a weekly email digest of stuck orders."}
        </div>
        <Link to="/profile?tab=sales" className="text-amber-800 font-semibold hover:underline" data-testid="escrow-view-all">
          {t("escrow.viewAll") || "View all sales →"}
        </Link>
      </div>
    </div>
  );
};

export default StuckEscrowAlerts;
