import React from "react";
import { Link } from "react-router-dom";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { Snowflake, Wallet as WalletIcon, Clock, Sparkles, TrendingUp, AlertTriangle } from "lucide-react";

/**
 * Balance Health Tile — a compact "money flow" card that surfaces how the
 * seller's escrow is behaving right now:
 *   • Total in-flight (frozen) vs available split (with a live gauge bar)
 *   • Number of open orders holding the frozen funds
 *   • Average + oldest days-in-flight so the seller can spot stuck escrow
 *   • Next expected release (ETA + listing thumb) — the "when's my money
 *     coming?" answer at a glance.
 */
const BalanceHealthTile = ({ health }) => {
  const { format } = useCurrency();
  const { t } = useLang();
  if (!health) return null;

  const {
    available = 0,
    frozen = 0,
    frozen_pct = 0,
    orders_in_flight = 0,
    avg_days_in_flight = 0,
    oldest_days_in_flight = 0,
    next_release = null,
  } = health;

  const totalFlow = available + frozen;
  const hasEscrow = frozen > 0 && orders_in_flight > 0;
  const availablePct = Math.max(0, 100 - frozen_pct);
  const oldestOverdue = oldest_days_in_flight >= 14; // ~2 weeks — soft alert

  const etaLabel = (() => {
    if (!next_release) return null;
    if (next_release.overdue) return t("wallet.health.overdue") || "Overdue — buyer hasn't confirmed";
    const days = next_release.eta_days;
    if (days === null || days === undefined) return t("wallet.health.pending") || "Pending buyer confirmation";
    if (days < 1) return t("wallet.health.today") || "Releases today";
    if (days < 2) return t("wallet.health.tomorrow") || "Releases tomorrow";
    return (t("wallet.health.inDays") || "Releases in ~{n} days").replace("{n}", String(Math.ceil(days)));
  })();

  return (
    <div
      className="rounded-2xl border border-neutral-200 bg-gradient-to-br from-white to-neutral-50 p-5 sm:p-6 shadow-sm"
      data-testid="balance-health-tile"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 text-white grid place-items-center">
            <TrendingUp className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-semibold text-neutral-900">
              {t("wallet.health.title") || "Balance health"}
            </div>
            <div className="text-[11px] text-neutral-500">
              {t("wallet.health.subtitle") || "Where your money is flowing right now"}
            </div>
          </div>
        </div>
        {hasEscrow && oldestOverdue && (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-800 text-[10px] font-semibold px-2 py-1 border border-amber-200"
            data-testid="balance-health-stuck-warning"
          >
            <AlertTriangle className="h-3 w-3" />
            {t("wallet.health.stuck") || "Stuck escrow"}
          </span>
        )}
      </div>

      {/* Split bar: available vs frozen */}
      {totalFlow > 0 ? (
        <>
          <div className="flex h-2.5 rounded-full overflow-hidden bg-neutral-100" data-testid="balance-health-bar">
            <div
              className="bg-gradient-to-r from-emerald-400 to-teal-500 transition-all duration-500"
              style={{ width: `${availablePct}%` }}
              title={t("wallet.available") || "Available"}
            />
            <div
              className="bg-gradient-to-r from-amber-300 to-amber-500 transition-all duration-500"
              style={{ width: `${frozen_pct}%` }}
              title={t("wallet.frozen") || "Frozen"}
            />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-neutral-500">
            <span className="inline-flex items-center gap-1"><WalletIcon className="h-3 w-3 text-emerald-600" /> {format(available)} · {availablePct.toFixed(0)}%</span>
            <span className="inline-flex items-center gap-1"><Snowflake className="h-3 w-3 text-amber-600" /> {format(frozen)} · {frozen_pct.toFixed(0)}%</span>
          </div>
        </>
      ) : (
        <div className="rounded-lg bg-neutral-50 border border-dashed border-neutral-200 text-[12px] text-neutral-500 p-3 text-center">
          {t("wallet.health.emptyState") || "No money in flight yet — your first sale will show up here."}
        </div>
      )}

      {/* Metrics grid */}
      {hasEscrow && (
        <div className="mt-4 grid grid-cols-3 gap-2" data-testid="balance-health-metrics">
          <div className="rounded-lg bg-white border border-neutral-200 p-2.5 text-center">
            <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">
              {t("wallet.health.inFlight") || "In flight"}
            </div>
            <div className="text-lg font-bold text-neutral-900 tabular-nums mt-0.5">{orders_in_flight}</div>
            <div className="text-[10px] text-neutral-400">
              {orders_in_flight === 1 ? (t("wallet.health.order") || "order") : (t("wallet.health.orders") || "orders")}
            </div>
          </div>
          <div className="rounded-lg bg-white border border-neutral-200 p-2.5 text-center">
            <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">
              {t("wallet.health.avgDays") || "Avg days"}
            </div>
            <div className="text-lg font-bold text-neutral-900 tabular-nums mt-0.5">{avg_days_in_flight}</div>
            <div className="text-[10px] text-neutral-400">{t("wallet.health.inEscrow") || "in escrow"}</div>
          </div>
          <div className={`rounded-lg bg-white border p-2.5 text-center ${oldestOverdue ? "border-amber-300" : "border-neutral-200"}`}>
            <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">
              {t("wallet.health.oldest") || "Oldest"}
            </div>
            <div className={`text-lg font-bold tabular-nums mt-0.5 ${oldestOverdue ? "text-amber-700" : "text-neutral-900"}`}>{oldest_days_in_flight}</div>
            <div className="text-[10px] text-neutral-400">{t("wallet.health.days") || "days"}</div>
          </div>
        </div>
      )}

      {/* Next release card */}
      {next_release && (
        <Link
          to="/profile?tab=sales"
          className="mt-4 flex items-center gap-3 rounded-xl border border-neutral-200 hover:border-emerald-400 bg-white p-3 transition"
          data-testid="balance-health-next-release"
        >
          {next_release.listing_image ? (
            <img
              src={next_release.listing_image}
              alt=""
              className="h-12 w-12 rounded-lg object-cover shrink-0"
              loading="lazy"
            />
          ) : (
            <div className="h-12 w-12 rounded-lg bg-neutral-100 grid place-items-center shrink-0">
              <Sparkles className="h-5 w-5 text-neutral-400" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold flex items-center gap-1">
              <Clock className="h-3 w-3" /> {t("wallet.health.nextRelease") || "Next release"}
            </div>
            <div className="text-sm font-semibold text-neutral-900 line-clamp-1 mt-0.5">
              {next_release.listing_title || t("wallet.health.orderFallback") || "Order"}
            </div>
            <div className={`text-[11px] font-medium mt-0.5 ${next_release.overdue ? "text-amber-700" : "text-emerald-700"}`}>
              {etaLabel}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-lg font-bold tabular-nums text-emerald-600">{format(next_release.amount)}</div>
            <div className="text-[10px] text-neutral-400">{t("wallet.health.willBecome") || "will unlock"}</div>
          </div>
        </Link>
      )}
    </div>
  );
};

export default BalanceHealthTile;
