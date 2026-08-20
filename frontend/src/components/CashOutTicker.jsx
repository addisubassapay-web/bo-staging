import React, { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { Sparkles, TrendingUp } from "lucide-react";

/**
 * Live Cash-Out Ticker — a subtle marquee that streams the most recent
 * frozen→available releases across the platform. Anonymized (`abcd…`) so
 * we surface social proof without leaking PII. Auto-hides when empty and
 * only mounts on non-mobile widths to avoid header clutter on small screens.
 */
const CashOutTicker = () => {
  const { format, currency } = useCurrency();
  const { t } = useLang();
  const [rows, setRows] = useState([]);
  const [paused, setPaused] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem("mercuri-global_ticker_dismissed") === "1"; } catch { return false; }
  });
  // Toggle: when true → show amounts in raw USD (source of truth) instead
  // of the picked currency. Lets an INR-browsing visitor peek at the
  // original dollar figure with a single click.
  const [showRaw, setShowRaw] = useState(() => {
    try { return localStorage.getItem("mercuri-global_ticker_raw_usd") === "1"; } catch { return false; }
  });
  const timerRef = useRef(null);

  useEffect(() => {
    if (dismissed) return undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const { data } = await api.get("/wallet/ticker", { params: { limit: 12, minutes: 240 } });
        if (!cancelled && Array.isArray(data)) setRows(data);
      } catch { /* silent — ticker is best-effort */ }
      if (!cancelled) timerRef.current = setTimeout(tick, 30_000);
    };

    tick();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [dismissed]);

  if (dismissed || rows.length === 0) return null;

  const dismiss = () => {
    setDismissed(true);
    try { localStorage.setItem("mercuri-global_ticker_dismissed", "1"); } catch { /* ignore */ }
  };

  const toggleRaw = () => {
    const next = !showRaw;
    setShowRaw(next);
    try { localStorage.setItem("mercuri-global_ticker_raw_usd", next ? "1" : "0"); } catch { /* ignore */ }
  };

  const showToggle = currency && currency !== "USD";
  const fmt = (usd) => (showRaw
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(usd)
    : format(usd));

  // Duplicate the row list so the marquee scrolls seamlessly.
  const doubled = [...rows, ...rows];

  return (
    <div
      className="hidden sm:block relative overflow-hidden border-b border-neutral-200/70 dark:border-neutral-800 bg-gradient-to-r from-emerald-50 via-white to-emerald-50 dark:from-emerald-950/30 dark:via-neutral-950 dark:to-emerald-950/30"
      data-testid="cash-out-ticker"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="max-w-screen-2xl mx-auto flex items-center gap-3 px-4 py-1.5">
        <div className="flex items-center gap-1.5 shrink-0 text-emerald-800 dark:text-emerald-300 text-[11px] font-semibold uppercase tracking-wider">
          <TrendingUp className="h-3 w-3" />
          {t("ticker.label") || "Live cash-outs"}
        </div>
        <div className="relative flex-1 overflow-hidden h-5">
          <div
            className={`ticker-track flex items-center gap-6 whitespace-nowrap absolute top-0 ${paused ? "ticker-paused" : ""}`}
            style={{ animationDuration: `${Math.max(20, doubled.length * 3)}s` }}
          >
            {doubled.map((r, i) => (
              <span key={i} className="flex items-center gap-1.5 text-xs text-neutral-700 dark:text-neutral-300">
                <Sparkles className="h-3 w-3 text-emerald-500" />
                <span className="font-semibold text-emerald-700 dark:text-emerald-400 tabular-nums">
                  +{fmt(r.amount)}
                </span>
                <span className="text-neutral-500">·</span>
                <span className="font-medium">{r.seller_masked}</span>
                {r.listing_title && (
                  <>
                    <span className="text-neutral-400">·</span>
                    <span className="text-neutral-500 truncate max-w-[240px]">{r.listing_title}</span>
                  </>
                )}
                <span className="text-neutral-400">·</span>
                <span className="text-[10px] text-neutral-400">
                  {r.ago_min < 1
                    ? (t("ticker.justNow") || "just now")
                    : (t("ticker.minAgo") || "{n}m ago").replace("{n}", String(r.ago_min))}
                </span>
              </span>
            ))}
          </div>
        </div>
        {showToggle && (
          <button
            type="button"
            onClick={toggleRaw}
            className="shrink-0 text-[10px] font-semibold rounded-full border border-emerald-200 dark:border-emerald-800 px-2 py-0.5 text-emerald-800 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 transition"
            title={showRaw
              ? (t("ticker.toggleBack") || `Show in ${currency}`).replace("{ccy}", currency)
              : (t("ticker.toggleUsd") || "Show original USD")}
            data-testid="cash-out-ticker-toggle"
          >
            {showRaw ? currency : "USD"}
          </button>
        )}
        <button
          type="button"
          onClick={dismiss}
          className="shrink-0 text-[10px] text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
          aria-label="Dismiss ticker"
          data-testid="cash-out-ticker-dismiss"
        >
          ✕
        </button>
      </div>
      <style>{`
        @keyframes ticker-scroll {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        .ticker-track {
          animation: ticker-scroll linear infinite;
          will-change: transform;
        }
        .ticker-paused { animation-play-state: paused; }
      `}</style>
    </div>
  );
};

export default CashOutTicker;
