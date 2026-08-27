import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { useToast } from "@/hooks/use-toast";
import { CheckCircle2, Lock, Share2, Wallet as WalletIcon, Plus } from "lucide-react";
import confetti from "canvas-confetti";

const Checkout = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { format } = useCurrency();
  const { t } = useLang();
  const { toast } = useToast();
  const [publicSettings, setPublicSettings] = useState({ delivery_days_estimate: 7 });
  const [listing, setListing] = useState(null);
  const [address, setAddress] = useState({ full_name: "", street: "", city: "", state: "", zip: "", country: "USA" });
  const [card, setCard] = useState({ number: "4242 4242 4242 4242", exp: "12/28", cvc: "123" });
  const [placing, setPlacing] = useState(false);
  const [done, setDone] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [savedAddress, setSavedAddress] = useState(null);
  const [coupon, setCoupon] = useState({ code: "", loading: false, discount: 0, description: "", error: "" });
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get(`/listings/${id}`).then((r) => setListing(r.data));
    api.get("/settings/public").then((r) => setPublicSettings(r.data)).catch(() => {});
    api.get("/wallet").then((r) => setWallet(r.data)).catch(() => {});
    // Prefill from most-recent order's shipping address
    api.get("/checkout/last-address").then((r) => {
      if (r.data?.has_saved) {
        setSavedAddress(r.data.address);
      }
    }).catch(() => {});
  }, [id, user, authLoading, navigate]);

  const applySavedAddress = () => {
    if (!savedAddress) return;
    setAddress({
      full_name: savedAddress.full_name || "",
      street: savedAddress.street || "",
      city: savedAddress.city || "",
      state: savedAddress.state || "",
      zip: savedAddress.zip || "",
      country: savedAddress.country || "USA",
    });
    toast({ title: "Address prefilled from your last order" });
  };

  const validateCoupon = async () => {
    if (!coupon.code.trim()) return;
    setCoupon((c) => ({ ...c, loading: true, error: "" }));
    try {
      const subtotal = listing ? Number(listing.price) : 0;
      const { data } = await api.post("/coupons/validate", {
        code: coupon.code.trim().toUpperCase(),
        subtotal,
        item_count: 1,
      });
      setCoupon({ code: data.code, loading: false, discount: data.discount, description: data.description, error: "" });
      toast({ title: `Coupon applied · -$${data.discount.toFixed(2)}` });
    } catch (err) {
      const msg = err.response?.data?.detail || "Coupon check failed";
      setCoupon((c) => ({ ...c, loading: false, discount: 0, description: "", error: msg }));
    }
  };

  const clearCoupon = () => setCoupon({ code: "", loading: false, discount: 0, description: "", error: "" });

  const place = async (e) => {
    e.preventDefault();
    if (!address.full_name || !address.street || !address.city || !address.zip) {
      toast({ title: t("checkout.completeAddress"), variant: "destructive" });
      return;
    }
    setPlacing(true);
    try {
      const affiliate_code = sessionStorage.getItem("affiliate_code") || null;
      const share_ref = sessionStorage.getItem("share_ref") || null;

      // Wallet-only checkout — server debits from wallet_balance via ledger.
      // If short, server responds HTTP 402 with a redirect to /wallet for top-up.
      const { data } = await api.post("/orders", { listing_id: id, quantity, shipping_address: address, affiliate_code, share_ref, payment_method: "wallet" });
      setDone(data);
      sessionStorage.removeItem("affiliate_code");
      sessionStorage.removeItem("share_ref");
      await api.delete(`/cart/${id}`).catch(() => {});
      // 🎉 Confetti burst on success
      requestAnimationFrame(() => {
        const end = Date.now() + 1500;
        const colors = ["#FF211F", "#FF7A18", "#FFD166", "#06D6A0", "#118AB2"];
        (function frame() {
          confetti({ particleCount: 5, angle: 60, spread: 55, startVelocity: 55, origin: { x: 0, y: 0.7 }, colors });
          confetti({ particleCount: 5, angle: 120, spread: 55, startVelocity: 55, origin: { x: 1, y: 0.7 }, colors });
          if (Date.now() < end) requestAnimationFrame(frame);
        })();
      });
    } catch (err) {
      // HTTP 402 = insufficient wallet balance. Redirect to /wallet with the
      // exact deposit amount pre-filled so the buyer can top up in one tap.
      const detail = err.response?.data?.detail;
      if (err.response?.status === 402 && detail && typeof detail === "object" && detail.deposit_needed) {
        toast({
          title: "Top up your wallet to place this order",
          description: detail.message || `Short by $${Number(detail.deposit_needed).toFixed(2)}. Opening the top-up page…`,
        });
        setTimeout(() => {
          navigate(`/wallet?open=deposit&suggested=${encodeURIComponent(Number(detail.deposit_needed).toFixed(2))}`);
        }, 800);
        return;
      }
      const msg = typeof detail === "string" ? detail : (detail?.message || t("checkout.tryAgain"));
      toast({ title: t("checkout.paymentFailed"), description: msg, variant: "destructive" });
    } finally {
      setPlacing(false);
    }
  };

  if (!listing) return <div className="max-w-3xl mx-auto px-4 py-8">Loading…</div>;

  if (done) {
    const shareUrl = `${window.location.origin}/listing/${done.listing_id || done.listing?.id || id}`;
    const shareText = `I just scored "${done.listing_title}" on Mercari-Smarthub! 🎉`;
    const doShare = async () => {
      if (navigator.share) {
        try { await navigator.share({ title: "Mercari-Smarthub", text: shareText, url: shareUrl }); }
        catch (e) { if (e?.name !== "AbortError") console.warn("[share] failed:", e); }
      } else {
        try {
          await navigator.clipboard.writeText(`${shareText} ${shareUrl}`);
          toast({ title: t("checkout.copied"), description: t("checkout.copiedDesc") });
        } catch (e) { console.warn("[share] clipboard failed:", e); }
      }
    };
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center" data-testid="checkout-success">
        <div className="relative inline-block">
          <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-2xl scale-125" />
          <div className="relative h-20 w-20 mx-auto rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 grid place-items-center shadow-xl">
            <CheckCircle2 className="h-10 w-10 text-white" />
          </div>
          <span className="absolute -top-1 -right-2 text-2xl">🎉</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold mt-5 tracking-tight text-neutral-900 dark:text-neutral-100">{t("checkout.orderPlaced")}</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-2">{t("checkout.notified").replace("{seller}", done.seller_name)}</p>
        <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 text-start text-sm space-y-1.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
          <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
            <span>{t("checkout.orderId")}</span>
            <span className="font-mono text-xs">{done.id.slice(0, 8)}</span>
          </div>
          <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
            <span>{t("checkout.item")}</span>
            <span className="text-right ml-2 line-clamp-1 max-w-[220px]">
              {done.listing_title}
              {done.quantity > 1 && <span className="ml-1 text-xs text-neutral-500">× {done.quantity}</span>}
            </span>
          </div>
          <div className="flex justify-between font-extrabold text-neutral-900 dark:text-neutral-100 text-base pt-1.5 border-t border-neutral-100 dark:border-neutral-800 mt-2">
            <span>{t("checkout.amount")}</span>
            <span className="tabular-nums">{format(done.amount + done.shipping_fee)}</span>
          </div>
        </div>
        <div className="mt-6 flex gap-2 justify-center flex-wrap">
          <Button variant="outline" onClick={doShare} className="gap-1.5 rounded-full" data-testid="checkout-share-btn">
            <Share2 className="h-4 w-4" /> {t("cta.share")}
          </Button>
          <Button variant="outline" className="rounded-full" onClick={() => navigate("/profile?tab=orders")}>{t("cta.viewOrders")}</Button>
          <Button className="bg-[#FF211F] hover:bg-[#e01d1b] rounded-full shadow-lg shadow-[#FF211F]/20" onClick={() => navigate("/")}>{t("cta.keepShopping")}</Button>
        </div>
      </div>
    );
  }

  const shippingFee = listing.shipping_paid_by === "buyer" ? 5.99 : 0;
  const unitPrice = listing.price;
  const gross = unitPrice * quantity;
  const bulkTiers = publicSettings.bulk_discount_tiers || [];
  const activeBulkTier = bulkTiers
    .filter((t) => quantity >= (t.min_qty || 0))
    .sort((a, b) => (b.min_qty || 0) - (a.min_qty || 0))[0];
  const bulkPct = activeBulkTier?.discount_pct || 0;
  const bulkAmount = Math.round(gross * bulkPct) / 100;
  const subtotal = gross - bulkAmount;
  const discount = coupon.discount || 0;
  const total = Math.max(0, subtotal + shippingFee - discount);
  const setQty = (n) => setQuantity(Math.max(1, Math.min(99, Number(n) || 1)));
  // What quantity unlocks the NEXT bulk tier? (shown as an upsell nudge)
  const nextBulkTier = bulkTiers
    .filter((t) => quantity < (t.min_qty || 0))
    .sort((a, b) => (a.min_qty || 0) - (b.min_qty || 0))[0];
  const deliveryDays = publicSettings.delivery_days_estimate || 7;
  const eta = new Date(Date.now() + deliveryDays * 24 * 60 * 60 * 1000);
  const etaLabel = eta.toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <div className="max-w-5xl w-full mx-auto px-3 sm:px-4 py-8 min-w-0 pb-28 lg:pb-8" data-testid="checkout-page">
      <div className="mb-8">
        <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
          {t("checkout.kicker")}
        </span>
        <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">{t("checkout.title")}</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{t("checkout.subtitle")}</p>
      </div>
      <form onSubmit={place} className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-6 lg:gap-8 min-w-0">
        <div className="space-y-4 min-w-0">
          <section className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] min-w-0">
            <div className="flex items-center justify-between mb-4 gap-2">
              <h2 className="font-bold text-lg text-neutral-900 dark:text-neutral-100">{t("checkout.shippingAddress")}</h2>
              {savedAddress && (
                <button
                  type="button"
                  onClick={applySavedAddress}
                  className="text-xs font-semibold px-3 py-1.5 rounded-full bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white hover:brightness-110 transition"
                  data-testid="prefill-saved-address"
                >
                  Use saved address
                </button>
              )}
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2"><Label>{t("checkout.fullName")}</Label><Input value={address.full_name} onChange={(e) => setAddress({ ...address, full_name: e.target.value })} required className="mt-1" /></div>
              <div className="sm:col-span-2"><Label>{t("checkout.street")}</Label><Input value={address.street} onChange={(e) => setAddress({ ...address, street: e.target.value })} required className="mt-1" /></div>
              <div><Label>{t("checkout.city")}</Label><Input value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} required className="mt-1" /></div>
              <div><Label>{t("checkout.state")}</Label><Input value={address.state} onChange={(e) => setAddress({ ...address, state: e.target.value })} required className="mt-1" /></div>
              <div><Label>{t("checkout.zip")}</Label><Input value={address.zip} onChange={(e) => setAddress({ ...address, zip: e.target.value })} required className="mt-1" /></div>
              <div><Label>{t("checkout.country")}</Label><Input value={address.country} onChange={(e) => setAddress({ ...address, country: e.target.value })} className="mt-1" /></div>
            </div>
          </section>

          <section className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] min-w-0">
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <div className="h-8 w-8 rounded-lg bg-emerald-50 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 grid place-items-center">
                <Lock className="h-4 w-4" />
              </div>
              <h2 className="font-bold text-lg text-neutral-900 dark:text-neutral-100">{t("checkout.payment")}</h2>
              <span className="ml-auto text-[10px] uppercase tracking-wider font-semibold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 rounded-full px-2 py-0.5">
                {t("checkout.demo")}
              </span>
            </div>

            {/* Wallet-only payment — Mercari-Smarthub orders debit the wallet
                directly. Top up first via /wallet (crypto or bank transfer,
                admin-approved) if the balance is short. */}
            <div className="mb-4 rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/60 dark:bg-emerald-500/10 px-4 py-3 flex items-start gap-3" data-testid="pay-method-wallet-only">
              <WalletIcon className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
              <div className="text-xs text-emerald-900 dark:text-emerald-200 leading-relaxed">
                <b>Paid from your wallet.</b> To fund your wallet, use crypto or bank transfer on the <button type="button" onClick={() => navigate("/wallet")} className="underline font-semibold hover:no-underline" data-testid="pay-wallet-link">Wallet page</button> — top-ups clear as soon as an admin verifies your payment screenshot.
              </div>
            </div>

            {/* Wallet balance panel */}
            <div className="animate-in fade-in-50 duration-200 rounded-2xl border-2 border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-500/10 p-4" data-testid="pay-wallet-panel">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-wider text-emerald-700 dark:text-emerald-300 font-semibold">Available balance</div>
                    <div className="text-3xl font-extrabold tabular-nums text-neutral-900 dark:text-neutral-100 mt-0.5">{format(wallet?.balance ?? 0)}</div>
                    {wallet?.frozen_balance > 0 && (
                      <div className="text-[11px] text-neutral-500 mt-0.5">Frozen: {format(wallet.frozen_balance)}</div>
                    )}
                  </div>
                  <WalletIcon className="h-10 w-10 text-emerald-500/60" />
                </div>
                {wallet && (wallet.balance ?? 0) < total ? (
                  <div className="mt-3">
                    <div className="text-xs text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-lg px-3 py-2 mb-2">
                      Insufficient balance. Short by <b>{format(total - (wallet.balance ?? 0))}</b>. Top up the difference to place this order.
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate("/wallet?open=deposit&suggested=" + encodeURIComponent(Math.max(10, total - (wallet.balance ?? 0)).toFixed(2)))}
                      className="w-full min-h-[44px] rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-semibold text-sm inline-flex items-center justify-center gap-2 shadow hover:brightness-110 transition"
                      data-testid="checkout-topup-wallet-btn"
                    >
                      <Plus className="h-4 w-4" /> Top up wallet
                    </button>
                    <p className="mt-1.5 text-[11px] text-neutral-500">
                      Top-ups accept crypto and bank transfer with screenshot proof — usually reviewed within a few minutes.
                    </p>
                  </div>
                ) : (
                  <p className="mt-3 text-[11px] text-emerald-700 dark:text-emerald-300">Order confirmation happens instantly with wallet payment.</p>
                )}
            </div>

          </section>
        </div>

        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5 h-fit lg:sticky lg:top-24 shadow-[0_1px_2px_rgba(0,0,0,0.04)] min-w-0">
          <h2 className="font-bold text-lg mb-4 text-neutral-900 dark:text-neutral-100">{t("cart.orderSummary")}</h2>
          <div className="flex gap-3 mb-4 pb-4 border-b border-neutral-100 dark:border-neutral-800 min-w-0">
            <img src={listing.images?.[0]} alt="" className="h-16 w-16 rounded-xl object-cover ring-1 ring-black/[0.04] dark:ring-white/10 shrink-0" />
            <div className="text-sm min-w-0 flex-1">
              <div className="font-semibold line-clamp-2 text-neutral-900 dark:text-neutral-100">{listing.title}</div>
              <div className="text-neutral-500 dark:text-neutral-400 text-xs mt-0.5">{t("cart.soldBy")} {listing.seller_name}</div>
            </div>
          </div>

          {/* Quantity — buy in bulk */}
          <div className="mb-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/60 px-3 py-2.5" data-testid="checkout-quantity-block">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-neutral-800 dark:text-neutral-100">Quantity</div>
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400 leading-tight mt-0.5">
                  Stock up on this item — bulk purchases ship together with one shipping fee.
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => setQty(quantity - 1)}
                  disabled={quantity <= 1}
                  aria-label="Decrease quantity"
                  data-testid="qty-decrease"
                  className="h-8 w-8 rounded-full border border-neutral-200 dark:border-neutral-700 grid place-items-center text-lg font-bold text-neutral-700 dark:text-neutral-200 hover:border-[#FF211F] hover:text-[#FF211F] disabled:opacity-40 disabled:cursor-not-allowed transition"
                >−</button>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={quantity}
                  onChange={(e) => setQty(e.target.value)}
                  aria-label="Quantity"
                  data-testid="qty-input"
                  className="h-8 w-12 text-center rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 text-sm font-bold tabular-nums focus:outline-none focus:ring-2 focus:ring-[#2563EB]/30"
                />
                <button
                  type="button"
                  onClick={() => setQty(quantity + 1)}
                  disabled={quantity >= 99}
                  aria-label="Increase quantity"
                  data-testid="qty-increase"
                  className="h-8 w-8 rounded-full border border-neutral-200 dark:border-neutral-700 grid place-items-center text-lg font-bold text-neutral-700 dark:text-neutral-200 hover:border-[#FF211F] hover:text-[#FF211F] disabled:opacity-40 transition"
                >+</button>
              </div>
            </div>
            {quantity >= 5 && (
              <div className="mt-2 text-[11px] text-emerald-700 dark:text-emerald-300 font-semibold" data-testid="bulk-badge">
                Bulk order · {quantity}× units
                {bulkPct > 0 && <span className="ml-1">· −{bulkPct}% applied</span>}
              </div>
            )}
            {nextBulkTier && quantity < nextBulkTier.min_qty && (
              <div className="mt-2 text-[11px] text-neutral-500 dark:text-neutral-400" data-testid="bulk-nudge">
                Add {nextBulkTier.min_qty - quantity} more to unlock <b className="text-emerald-700 dark:text-emerald-300">{nextBulkTier.discount_pct}% off</b>
              </div>
            )}
          </div>

          <div className="space-y-2.5 text-sm">
            <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
              <span>
                {t("checkout.item")}
                {quantity > 1 && <span className="text-neutral-400 dark:text-neutral-500"> · {format(unitPrice)} × {quantity}</span>}
              </span>
              <span className="tabular-nums font-medium" data-testid="summary-subtotal">{format(gross)}</span>
            </div>
            {bulkAmount > 0 && (
              <div className="flex justify-between text-emerald-700 dark:text-emerald-400" data-testid="bulk-discount-row">
                <span>Bulk discount ({bulkPct}% off for {quantity}+ units)</span>
                <span className="tabular-nums font-medium">−{format(bulkAmount)}</span>
              </div>
            )}
            <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
              <span>{t("cart.shipping")}</span>
              <span className="tabular-nums font-medium">{format(shippingFee)}</span>
            </div>

            {/* Coupon field with instant validation */}
            <div className="pt-3 mt-1 border-t border-neutral-100 dark:border-neutral-800">
              {coupon.discount > 0 ? (
                <div className="flex items-center justify-between rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 px-3 py-2" data-testid="coupon-applied">
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-emerald-800 dark:text-emerald-200 truncate">{coupon.code} · -{format(coupon.discount)}</div>
                    <div className="text-[11px] text-emerald-700 dark:text-emerald-300 truncate">{coupon.description}</div>
                  </div>
                  <button type="button" onClick={clearCoupon} className="text-emerald-700 hover:text-emerald-900 text-xs font-medium" data-testid="coupon-clear">Remove</button>
                </div>
              ) : (
                <div>
                  <label className="text-xs font-semibold text-neutral-500 dark:text-neutral-400">Have a coupon?</label>
                  <div className="mt-1 flex gap-2">
                    <input
                      value={coupon.code}
                      onChange={(e) => setCoupon((c) => ({ ...c, code: e.target.value.toUpperCase(), error: "" }))}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), validateCoupon())}
                      placeholder="WELCOME10"
                      className="flex-1 h-10 px-3 rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm font-mono uppercase tracking-wider focus:outline-none focus:ring-2 focus:ring-[#2563EB]/30 focus:border-[#2563EB] transition"
                      data-testid="coupon-input"
                      maxLength={20}
                    />
                    <button type="button" onClick={validateCoupon} disabled={coupon.loading || !coupon.code.trim()} className="h-10 px-4 rounded-md bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white text-sm font-semibold hover:brightness-110 disabled:opacity-50 transition" data-testid="coupon-apply">
                      {coupon.loading ? "…" : "Apply"}
                    </button>
                  </div>
                  {coupon.error && <div className="text-[11px] text-red-600 dark:text-red-400 mt-1" data-testid="coupon-error">{coupon.error}</div>}
                </div>
              )}
            </div>

            {coupon.discount > 0 && (
              <div className="flex justify-between text-emerald-700 dark:text-emerald-400">
                <span>Coupon discount</span>
                <span className="tabular-nums font-medium">-{format(coupon.discount)}</span>
              </div>
            )}

            <div className="rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 px-3 py-2 text-xs text-emerald-800 dark:text-emerald-200 flex items-center gap-2" data-testid="checkout-delivery-eta">
              <Lock className="h-3.5 w-3.5 shrink-0" />
              <div>
                <div className="font-semibold">Arrives in ~{deliveryDays} days · by {etaLabel}</div>
                <div className="opacity-80 mt-0.5">Seller earnings stay frozen until you confirm delivery.</div>
              </div>
            </div>
            <div className="h-px bg-neutral-200 dark:bg-neutral-800 my-3" />
            <div className="flex justify-between font-extrabold text-lg text-neutral-900 dark:text-neutral-100">
              <span>{t("cart.total")}</span>
              <span className="tabular-nums">{format(total)}</span>
            </div>
          </div>
          <Button
            type="submit"
            disabled={placing || (wallet && (wallet.balance ?? 0) < total)}
            className="w-full mt-5 bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 rounded-full h-12 min-h-[48px] font-bold shadow-lg shadow-[#FF211F]/30 disabled:opacity-60 hover:-translate-y-0.5 active:translate-y-0 transition-all hidden lg:block"
            data-testid="place-order-btn"
          >
            {placing ? t("checkout.placing") : `${t("checkout.pay")} ${format(total)}`}
          </Button>
        </div>
      </form>

      {/* Sticky mobile action bar — visible only on <lg screens */}
      <div
        className="lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-neutral-200 dark:border-neutral-800 bg-white/95 dark:bg-neutral-950/95 backdrop-blur px-4 py-3 flex items-center justify-between gap-3 shadow-[0_-4px_16px_rgba(0,0,0,0.08)] safe-bottom"
        data-testid="sticky-checkout-bar"
      >
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-widest text-neutral-500 dark:text-neutral-400">{t("cart.total")}</div>
          <div className="text-lg font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(total)}</div>
        </div>
        <Button
          type="button"
          onClick={place}
          disabled={placing || (wallet && (wallet.balance ?? 0) < total)}
          className="flex-1 max-w-[240px] bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 rounded-full h-12 min-h-[48px] font-bold shadow-lg shadow-[#FF211F]/30 disabled:opacity-60 transition-all"
          data-testid="place-order-mobile-btn"
        >
          {placing ? t("checkout.placing") : t("checkout.pay")}
        </Button>
      </div>
    </div>
  );
};

export default Checkout;
