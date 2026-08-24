import React, { useState, useCallback } from "react";
import api, { formatPrice } from "@/lib/api";
import { ChevronDown, ChevronUp, Snowflake, ArrowDownCircle, ArrowUpCircle, CheckCircle2, Coins, Gift, Users } from "lucide-react";

/**
 * Per-order wallet activity timeline. Renders a compact list of every
 * ledger event tied to an order (buyer paid, seller escrow held, wholesale
 * debit, delivery released, affiliate / referral payouts, refunds).
 *
 * Collapsed by default — the parent renders one toggle per order row so the
 * feed doesn't blow up long lists. Fetched lazily on first expand.
 */

const ROLE_META = {
  buyer_paid:                 { icon: ArrowUpCircle,   label: "You paid the seller",             tint: "text-rose-700 bg-rose-50 border-rose-200" },
  seller_credited:            { icon: ArrowDownCircle, label: "Sale credited",                   tint: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  seller_escrow_held:         { icon: Snowflake,       label: "Buyer paid — earnings on hold",   tint: "text-sky-800 bg-sky-50 border-sky-200" },
  seller_wholesale_paid:      { icon: ArrowUpCircle,   label: "Wholesale paid at Pick & Deliver", tint: "text-amber-800 bg-amber-50 border-amber-200" },
  seller_delivery_released:   { icon: CheckCircle2,    label: "Delivery confirmed — funds released", tint: "text-emerald-800 bg-emerald-50 border-emerald-200" },
  dropship_source_escrow_held:{ icon: Snowflake,       label: "Dropship earnings on hold",       tint: "text-sky-800 bg-sky-50 border-sky-200" },
  dropship_source_released:   { icon: CheckCircle2,    label: "Dropship earnings released",      tint: "text-emerald-800 bg-emerald-50 border-emerald-200" },
  dropship_source_credited:   { icon: Coins,           label: "Dropship payout",                 tint: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  affiliate_paid:             { icon: Gift,            label: "Affiliate commission",            tint: "text-fuchsia-800 bg-fuchsia-50 border-fuchsia-200" },
  referral_paid:              { icon: Users,           label: "Referral bonus",                  tint: "text-indigo-800 bg-indigo-50 border-indigo-200" },
  refunded:                   { icon: ArrowDownCircle, label: "Refunded",                        tint: "text-rose-700 bg-rose-50 border-rose-200" },
};

const fmtTime = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
};

const OrderWalletTimeline = ({ orderId, initialOpen = false }) => {
  const [open, setOpen] = useState(initialOpen);
  const [loading, setLoading] = useState(false);
  const [events, setEvents] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (events || loading) return;
    setLoading(true);
    setErr("");
    try {
      const r = await api.get(`/orders/${orderId}/wallet-events`);
      setEvents(r.data?.events || []);
    } catch (e) {
      setErr(e.response?.data?.detail || "Couldn't load activity");
    } finally {
      setLoading(false);
    }
  }, [orderId, events, loading]);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) load();
  };

  return (
    <div className="mt-3" data-testid={`wallet-timeline-${orderId}`}>
      <button
        type="button"
        onClick={toggle}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-600 dark:text-neutral-300 hover:text-[#FF211F] transition"
        data-testid={`wallet-timeline-toggle-${orderId}`}
      >
        <Coins className="h-3.5 w-3.5" />
        {open ? "Hide" : "Wallet activity"}
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>

      {open && (
        <div className="mt-2 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50/70 dark:bg-neutral-900/60 p-3" data-testid={`wallet-timeline-body-${orderId}`}>
          {loading && <div className="text-xs text-neutral-500">Loading activity…</div>}
          {!loading && err && <div className="text-xs text-red-600">{err}</div>}
          {!loading && !err && events && events.length === 0 && (
            <div className="text-xs text-neutral-500">No wallet events recorded for this order yet.</div>
          )}
          {!loading && !err && events && events.length > 0 && (
            <ol className="space-y-2" data-testid={`wallet-timeline-list-${orderId}`}>
              {events.map((e, idx) => {
                const meta = ROLE_META[e.role] || { icon: Coins, label: e.description || e.type, tint: "text-neutral-700 bg-neutral-100 border-neutral-200" };
                const Icon = meta.icon;
                const positive = (Number(e.amount) || 0) > 0;
                return (
                  <li key={`${e.id || idx}-${e.type}`} className="flex items-start gap-2.5" data-testid={`wallet-timeline-row-${idx}`}>
                    <span className={`shrink-0 h-7 w-7 rounded-full grid place-items-center border ${meta.tint}`}>
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold text-neutral-900 dark:text-neutral-100">{meta.label}</div>
                      {e.description && (
                        <div className="text-[11px] text-neutral-500 line-clamp-1">{e.description}</div>
                      )}
                      <div className="text-[10px] text-neutral-400 mt-0.5">{fmtTime(e.created_at)}{e.bucket ? ` · ${e.bucket}` : ""}</div>
                    </div>
                    <div className={`text-xs font-bold tabular-nums whitespace-nowrap ${positive ? "text-emerald-700" : "text-rose-700"}`}>
                      {positive ? "+" : ""}{formatPrice(e.amount)}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
};

export default OrderWalletTimeline;
