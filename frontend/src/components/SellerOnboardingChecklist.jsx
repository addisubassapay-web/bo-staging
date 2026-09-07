import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Store, Package, Wallet, Share2, ArrowRight } from "lucide-react";
import api from "@/lib/api";

/**
 * SellerOnboardingChecklist — a 4-step tap-and-go card that lives on
 * `/dashboard/seller` for new sellers. Shows completion state pulled
 * from the seller's own store / listings / payout method / share flag.
 *
 * The checklist self-dismisses via localStorage once all four steps
 * are checked so it doesn't clutter power-sellers' dashboards.
 */
const STORAGE_KEY = "blueocean_seller_onboarding_dismissed";

const useChecklistState = () => {
  const [state, setState] = useState({
    loading: true,
    hasListing: false,
    hasPayout: false,
    hasLogo: false,
    hasShared: false,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [listings, store] = await Promise.all([
          api.get("/my/listings", { params: { limit: 1 } }).catch(() => ({ data: [] })),
          api.get("/my/store").catch(() => ({ data: {} })),
        ]);
        if (cancelled) return;
        const s = store?.data || {};
        setState({
          loading: false,
          hasListing: (listings?.data?.length || 0) > 0,
          hasPayout: !!(s.payout_method || s.crypto_addresses),
          hasLogo: !!s.logo,
          hasShared: localStorage.getItem("blueocean_seller_shared_v1") === "1",
        });
      } catch {
        if (!cancelled) setState((p) => ({ ...p, loading: false }));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return state;
};

const Row = ({ done, title, cta, ctaHref, testid, onCta }) => (
  <div
    className={`flex items-center gap-3 rounded-xl px-3 py-3 transition ${done ? "bg-emerald-50 dark:bg-emerald-950/30" : "bg-neutral-50 dark:bg-neutral-800/60 hover:bg-white dark:hover:bg-neutral-800"}`}
    data-testid={testid}
  >
    <span className="shrink-0">
      {done ? (
        <CheckCircle2 className="h-6 w-6 text-emerald-500" />
      ) : (
        <Circle className="h-6 w-6 text-neutral-400" />
      )}
    </span>
    <div className="flex-1 min-w-0">
      <div className={`text-sm font-bold ${done ? "text-emerald-800 dark:text-emerald-300 line-through decoration-emerald-400" : "text-[#5459E8] dark:text-[#818CF8]"}`}>
        {title}
      </div>
    </div>
    {!done && (
      ctaHref ? (
        <Link to={ctaHref}>
          <button className="text-xs font-semibold px-3 h-8 rounded-full bg-gradient-to-r from-[#5459E8] to-[#818CF8] text-white hover:brightness-110 inline-flex items-center gap-1">
            {cta} <ArrowRight className="h-3 w-3" />
          </button>
        </Link>
      ) : (
        <button
          onClick={onCta}
          className="text-xs font-semibold px-3 h-8 rounded-full bg-gradient-to-r from-[#FF0515] to-[#FF5B6B] text-white hover:brightness-110 inline-flex items-center gap-1"
        >
          {cta} <ArrowRight className="h-3 w-3" />
        </button>
      )
    )}
  </div>
);

export const SellerOnboardingChecklist = ({ storeSlug }) => {
  const s = useChecklistState();
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) === "1"; } catch { return false; }
  });

  const total = 4;
  const done = [s.hasListing, s.hasPayout, s.hasLogo, s.hasShared].filter(Boolean).length;
  const allDone = done === total;

  if (dismissed || s.loading) return null;

  const share = () => {
    const url = storeSlug ? `${window.location.origin}/store/${storeSlug}` : window.location.origin;
    const text = "Check out my BlueOcean store!";
    if (navigator.share) {
      navigator.share({ title: "BlueOcean", text, url }).catch(() => {});
    } else {
      navigator.clipboard?.writeText(url).catch(() => {});
    }
    try { localStorage.setItem("blueocean_seller_shared_v1", "1"); } catch { /* ignore */ }
    window.location.reload();
  };

  return (
    <div
      className="relative rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 sm:p-6 shadow-sm card-lift"
      data-testid="seller-onboarding-checklist"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-[#FF0515] font-extrabold">Getting started</div>
          <div className="mt-1 text-xl font-extrabold text-neutral-900 dark:text-neutral-100">
            {allDone ? "You're all set! 🎉" : `Ship your first sale in ${total - done} step${total - done > 1 ? "s" : ""}`}
          </div>
        </div>
        {allDone && (
          <button
            className="text-xs text-neutral-500 hover:text-[#5459E8]"
            onClick={() => { try { localStorage.setItem(STORAGE_KEY, "1"); } catch { /* ignore */ } setDismissed(true); }}
            data-testid="checklist-dismiss"
          >
            Dismiss
          </button>
        )}
      </div>
      <div className="h-2 rounded-full bg-neutral-100 dark:bg-neutral-800 overflow-hidden mb-4">
        <div
          className="h-full bg-gradient-to-r from-[#5459E8] to-[#FF0515] transition-all"
          style={{ width: `${(done / total) * 100}%` }}
          data-testid="checklist-progress-bar"
        />
      </div>
      <div className="space-y-2">
        <Row done={s.hasListing} title="List your first item"
             cta="List now" ctaHref="/sell" testid="checklist-step-list" />
        <Row done={s.hasPayout} title="Connect your payout method"
             cta="Set payout" ctaHref="/wallet?tab=payout" testid="checklist-step-payout" />
        <Row done={s.hasLogo} title="Add your store logo"
             cta="Upload logo" ctaHref="/my/store" testid="checklist-step-logo" />
        <Row done={s.hasShared} title="Share your store link"
             cta="Share now" onCta={share} testid="checklist-step-share" />
      </div>
    </div>
  );
};

export default SellerOnboardingChecklist;
