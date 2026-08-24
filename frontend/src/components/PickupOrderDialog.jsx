import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Loader2, PackageCheck, Wallet, Snowflake, AlertTriangle, Info, Timer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/hooks/use-toast";
import { Link } from "react-router-dom";

const fmt = (n) => `$${Number(n ?? 0).toFixed(2)}`;

/**
 * PickupOrderDialog — modal that shows the cost breakdown, wallet balances,
 * and the "Pick and Deliver" call-to-action. Debits wholesale from wallet
 * (with optional frozen-reinvest up to 75% cap) via the /pickup endpoint.
 *
 * Props:
 *   orderId: string
 *   trigger: ReactNode (optional custom trigger)
 *   onPicked: (updatedOrder) => void
 */
const PickupOrderDialog = ({ orderId, trigger, onPicked }) => {
  const [open, setOpen] = useState(false);
  const [quote, setQuote] = useState(null);
  const [useFrozen, setUseFrozen] = useState(false);
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  const loadQuote = useCallback(async () => {
    try {
      const { data } = await api.get(`/orders/${orderId}/pickup-quote`);
      setQuote(data);
    } catch (e) {
      toast({
        title: "Failed to load pickup quote",
        description: e?.response?.data?.detail || "Try again in a moment",
        variant: "destructive",
      });
      setOpen(false);
    }
  }, [orderId, toast]);

  useEffect(() => {
    if (open) loadQuote();
  }, [open, loadQuote]);

  const pick = async () => {
    if (busy || !quote) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/orders/${orderId}/pickup`, {
        use_frozen: useFrozen,
      });
      toast({
        title: "Order picked up",
        description: `${fmt(quote.cost)} paid · profit ${fmt(quote.profit)} locked until delivery`,
      });
      setOpen(false);
      onPicked?.(data);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (typeof detail === "object" && detail?.code === "insufficient_funds") {
        toast({
          title: "Insufficient funds",
          description: `Deposit ${fmt(detail.deposit_needed)} or tick "use frozen balance" to fund this pickup.`,
          variant: "destructive",
        });
      } else {
        toast({
          title: "Pickup failed",
          description: typeof detail === "string" ? detail : "Try again in a moment",
          variant: "destructive",
        });
      }
    } finally {
      setBusy(false);
    }
  };

  const affordable = quote && (useFrozen ? quote.affordable_with_frozen : quote.affordable_from_available);

  return (
    <>
      <span onClick={() => setOpen(true)} data-testid={`pickup-trigger-${orderId}`}>
        {trigger || (
          <Button
            size="sm"
            className="bg-[#FF211F] hover:bg-[#e01a19] text-white rounded-full"
            data-testid={`pickup-btn-${orderId}`}
          >
            <PackageCheck className="h-4 w-4 mr-1.5" /> Pick & Deliver
          </Button>
        )}
      </span>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="pickup-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PackageCheck className="h-5 w-5 text-[#FF211F]" />
              Pick & Deliver order
            </DialogTitle>
            <DialogDescription>
              Pay the source cost from your wallet to accept the order and start fulfillment.
            </DialogDescription>
          </DialogHeader>

          {!quote ? (
            <div className="py-8 text-center text-neutral-500 text-sm">
              <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading quote…
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-sm">
                <div className="font-medium text-neutral-900 line-clamp-2" data-testid="pickup-listing-title">
                  {quote.listing_title}
                </div>
                <div className="text-xs text-neutral-500 mt-0.5">Quantity: {quote.quantity}</div>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-neutral-600">Source cost you pay</span>
                  <span className="font-semibold text-neutral-900" data-testid="pickup-cost">{fmt(quote.cost)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-600">Your profit (held until delivery)</span>
                  <span className="font-semibold text-emerald-700" data-testid="pickup-profit">{fmt(quote.profit)}</span>
                </div>
                {quote.hours_left !== null && (
                  <div className="flex justify-between text-xs text-amber-700">
                    <span className="inline-flex items-center gap-1"><Timer className="h-3 w-3" /> Time left to accept</span>
                    <span>{quote.hours_left}h</span>
                  </div>
                )}
              </div>

              {/* Wallet snapshot */}
              <div className="rounded-lg border border-neutral-200 p-3 space-y-2 text-sm">
                <div className="flex items-center gap-2 text-xs font-semibold text-neutral-500 uppercase tracking-wider">
                  <Wallet className="h-3.5 w-3.5" /> Your wallet
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-600">Available</span>
                  <span className="font-mono" data-testid="pickup-wallet-available">{fmt(quote.wallet.available)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-600 inline-flex items-center gap-1">
                    <Snowflake className="h-3.5 w-3.5 text-blue-500" /> Frozen (75% reinvestable)
                  </span>
                  <span className="font-mono" data-testid="pickup-wallet-frozen">
                    {fmt(quote.wallet.frozen)} <span className="text-neutral-400">/ {fmt(quote.wallet.frozen_usable)}</span>
                  </span>
                </div>
              </div>

              {/* Use frozen toggle */}
              <label
                className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border border-neutral-200 hover:bg-neutral-50 transition-colors"
                data-testid="pickup-use-frozen-label"
              >
                <Checkbox
                  checked={useFrozen}
                  onCheckedChange={(v) => setUseFrozen(Boolean(v))}
                  data-testid="pickup-use-frozen-checkbox"
                  className="mt-0.5"
                />
                <div className="flex-1 text-sm">
                  <div className="font-medium text-neutral-900 inline-flex items-center gap-1.5">
                    <Snowflake className="h-3.5 w-3.5 text-blue-500" /> Use frozen balance too
                  </div>
                  <div className="text-xs text-neutral-500 mt-0.5">
                    Reinvest up to 75% of your frozen earnings ({fmt(quote.wallet.frozen_usable)}) to fund this pickup. Frozen funds can only be reinvested to initiate order delivery.
                  </div>
                </div>
              </label>

              {/* Affordability banner */}
              {!affordable ? (
                <div
                  className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2 text-sm"
                  data-testid="pickup-insufficient"
                >
                  <div className="flex items-start gap-2 font-medium text-amber-900">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                    Not enough funds to pick this order
                  </div>
                  <div className="text-xs text-amber-800">
                    You still need <span className="font-semibold">{fmt(quote.deposit_needed - (useFrozen ? 0 : quote.wallet.frozen_usable))}</span>{" "}
                    {useFrozen ? "in your wallet" : "— or tick 'Use frozen balance too' to unlock more"}.
                  </div>
                  <Link
                    to="/wallet"
                    onClick={() => setOpen(false)}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#FF211F] hover:underline"
                    data-testid="pickup-deposit-link"
                  >
                    Deposit into wallet →
                  </Link>
                </div>
              ) : (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800 flex items-start gap-2">
                  <Info className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  You have enough to pick this order. Your buyer&apos;s payment stays in escrow until you deliver.
                </div>
              )}
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={pick}
              disabled={busy || !quote || !affordable}
              className="bg-[#FF211F] hover:bg-[#e01a19] text-white"
              data-testid="pickup-confirm-btn"
            >
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Debiting…
                </>
              ) : (
                <>
                  <PackageCheck className="h-4 w-4 mr-1.5" /> Confirm & pay {quote ? fmt(quote.cost) : ""}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default PickupOrderDialog;
