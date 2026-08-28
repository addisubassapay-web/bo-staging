import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PartyPopper, Store as StoreIcon, ArrowRight, ExternalLink, Sparkles, TrendingUp, Truck } from "lucide-react";

/**
 * StoreApprovedModal — celebratory notification card that pops when a
 * seller's store status flips to APPROVED. Shows a summary of their store
 * (name, slug, tier, storefront theme) and two CTAs:
 *   • primary → /dashboard/seller (Manage your storefront)
 *   • secondary → /store/{slug}   (View my public store)
 *
 * Controlled component: parent decides open state. Fires `onClose` once
 * dismissed so the parent can flip a "already-celebrated" flag.
 */
export const StoreApprovedModal = ({
  open,
  onOpenChange,
  store = null,
  user = null,
}) => {
  const navigate = useNavigate();
  const [confetti, setConfetti] = useState(false);

  useEffect(() => {
    if (open) {
      setConfetti(true);
      const t = setTimeout(() => setConfetti(false), 2200);
      return () => clearTimeout(t);
    }
  }, [open]);

  const storeName = store?.name || user?.username || "your store";
  const storeSlug = store?.slug || (user?.username || "").toLowerCase().replace(/\s+/g, "-");
  const tier = store?.tier || "trusted";
  const theme = store?.theme || "Modern Storefront";

  const goDashboard = () => {
    onOpenChange?.(false);
    navigate("/dashboard/seller");
  };
  const viewPublic = () => {
    onOpenChange?.(false);
    navigate(storeSlug ? `/store/${storeSlug}` : "/my/store");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-lg p-0 overflow-hidden border-0 rounded-2xl"
        data-testid="store-approved-modal"
      >
        {/* Aurora header */}
        <div className="relative bg-gradient-to-br from-[#FF7A18] via-[#FF211F] to-[#c1197c] px-6 pt-6 pb-14 text-white">
          {confetti && (
            <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden>
              {Array.from({ length: 24 }).map((_, i) => (
                <span
                  key={i}
                  className="absolute block w-2 h-2 rounded-sm animate-confetti"
                  style={{
                    left: `${(i * 4.1) % 100}%`,
                    top: "-10px",
                    background: ["#fff", "#FFD166", "#06D6A0", "#FDE68A", "#F472B6"][i % 5],
                    animationDelay: `${(i % 6) * 120}ms`,
                    animationDuration: `${1800 + (i % 5) * 250}ms`,
                    transform: `rotate(${(i * 37) % 360}deg)`,
                  }}
                />
              ))}
            </div>
          )}
          <div className="relative flex items-start gap-3">
            <div className="h-12 w-12 rounded-2xl bg-white/20 backdrop-blur grid place-items-center shadow-lg">
              <PartyPopper className="h-6 w-6" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-[0.24em] font-semibold text-white/80">Approved</div>
              <DialogTitle className="text-2xl font-extrabold mt-0.5 tracking-tight leading-tight">
                Your store is live!
              </DialogTitle>
              <DialogDescription className="text-white/90 text-sm mt-1">
                Welcome to Mercari-Smarthub, {user?.first_name || user?.username || "seller"}.
              </DialogDescription>
            </div>
          </div>
        </div>

        {/* Store card — pulls up over the aurora */}
        <div className="px-6 -mt-8">
          <div
            className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-xl shadow-black/5"
            data-testid="store-approved-summary"
          >
            <div className="flex items-center gap-3">
              <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-neutral-900 to-neutral-700 text-white grid place-items-center">
                <StoreIcon className="h-5 w-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-extrabold truncate" data-testid="store-approved-name">
                  {storeName}
                </div>
                <div className="text-xs text-neutral-500 truncate font-mono">
                  mercariglobals.com/store/{storeSlug || "your-slug"}
                </div>
              </div>
              <Badge
                variant="secondary"
                className="capitalize bg-emerald-100 text-emerald-800 hover:bg-emerald-100"
                data-testid="store-approved-tier"
              >
                {tier}
              </Badge>
            </div>

            {/* Storefront theme + perks */}
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-neutral-50 dark:bg-neutral-800/60 p-3">
                <Sparkles className="h-4 w-4 mx-auto text-[#FF7A18]" />
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 mt-1">Theme</div>
                <div className="text-xs font-semibold mt-0.5 truncate" title={theme}>{theme}</div>
              </div>
              <div className="rounded-xl bg-neutral-50 dark:bg-neutral-800/60 p-3">
                <TrendingUp className="h-4 w-4 mx-auto text-emerald-600" />
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 mt-1">Fee</div>
                <div className="text-xs font-semibold mt-0.5">10% flat</div>
              </div>
              <div className="rounded-xl bg-neutral-50 dark:bg-neutral-800/60 p-3">
                <Truck className="h-4 w-4 mx-auto text-sky-600" />
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 mt-1">Payouts</div>
                <div className="text-xs font-semibold mt-0.5">Weekly</div>
              </div>
            </div>
          </div>
        </div>

        {/* CTAs */}
        <div className="px-6 py-5 flex flex-col sm:flex-row gap-2">
          <Button
            onClick={goDashboard}
            className="flex-1 bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-11 shadow-lg shadow-[#FF211F]/25"
            data-testid="store-approved-primary-cta"
          >
            Manage storefront <ArrowRight className="h-4 w-4 ml-1.5" />
          </Button>
          <Button
            variant="outline"
            onClick={viewPublic}
            className="flex-1 rounded-full h-11"
            data-testid="store-approved-secondary-cta"
          >
            View public page <ExternalLink className="h-4 w-4 ml-1.5" />
          </Button>
        </div>
      </DialogContent>

      {/* Local styles for confetti animation */}
      <style>{`
        @keyframes confetti-fall {
          0%   { transform: translateY(-10px) rotate(0deg); opacity: 1; }
          100% { transform: translateY(320px) rotate(720deg); opacity: 0; }
        }
        .animate-confetti { animation: confetti-fall linear forwards; }
      `}</style>
    </Dialog>
  );
};

export default StoreApprovedModal;
