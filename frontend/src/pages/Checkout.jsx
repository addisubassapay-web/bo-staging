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
import { CheckCircle2, Lock, Share2, CreditCard, Wallet as WalletIcon, Bitcoin, Building2, Copy, Check } from "lucide-react";
import confetti from "canvas-confetti";

const qrUrl = (data) => `https://api.qrserver.com/v1/create-qr-code/?size=180x180&margin=0&data=${encodeURIComponent(data || "")}`;

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
  const [payMethod, setPayMethod] = useState("card"); // card | wallet | crypto | bank
  const [wallet, setWallet] = useState(null);
  const [payMethods, setPayMethods] = useState({ crypto_addresses: {}, crypto_assets: [], manual_payment_methods: [] });
  const [assetId, setAssetId] = useState("");
  const [cryptoCcy, setCryptoCcy] = useState("");
  const [bankId, setBankId] = useState("");
  const [copied, setCopied] = useState("");
  const [savedAddress, setSavedAddress] = useState(null);
  const [coupon, setCoupon] = useState({ code: "", loading: false, discount: 0, description: "", error: "" });

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get(`/listings/${id}`).then((r) => setListing(r.data));
    api.get("/settings/public").then((r) => setPublicSettings(r.data)).catch(() => {});
    api.get("/wallet").then((r) => setWallet(r.data)).catch(() => {});
    api.get("/wallet/payment-methods").then((r) => {
      const d = r.data || {};
      setPayMethods({ crypto_addresses: d.crypto_addresses || {}, crypto_assets: d.crypto_assets || [], manual_payment_methods: d.manual_payment_methods || [] });
      const firstAsset = (d.crypto_assets || [])[0];
      if (firstAsset) setAssetId(firstAsset.id);
      const first = Object.keys(d.crypto_addresses || {})[0];
      if (first) setCryptoCcy(first);
      const m = (d.manual_payment_methods || [])[0];
      if (m) setBankId(m.id);
    }).catch(() => {});
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
      const { data } = await api.post("/checkout/coupon/validate", {
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

  const doCopy = async (text, key) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    } catch (e) { /* ignore */ }
  };

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
      const { data } = await api.post("/orders", { listing_id: id, shipping_address: address, affiliate_code, share_ref, payment_method: payMethod });
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
      toast({ title: t("checkout.paymentFailed"), description: err.response?.data?.detail || t("checkout.tryAgain"), variant: "destructive" });
    } finally {
      setPlacing(false);
    }
  };

  if (!listing) return <div className="max-w-3xl mx-auto px-4 py-8">Loading…</div>;

  if (done) {
    const shareUrl = `${window.location.origin}/listing/${done.listing_id || done.listing?.id || id}`;
    const shareText = `I just scored "${done.listing_title}" on Mercari Global! 🎉`;
    const doShare = async () => {
      if (navigator.share) {
        try { await navigator.share({ title: "Mercari Global", text: shareText, url: shareUrl }); } catch { /* cancelled */ }
      } else {
        try {
          await navigator.clipboard.writeText(`${shareText} ${shareUrl}`);
          toast({ title: t("checkout.copied"), description: t("checkout.copiedDesc") });
        } catch { /* ignore */ }
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
        <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 text-left text-sm space-y-1.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
          <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
            <span>{t("checkout.orderId")}</span>
            <span className="font-mono text-xs">{done.id.slice(0, 8)}</span>
          </div>
          <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
            <span>{t("checkout.item")}</span>
            <span className="text-right ml-2 line-clamp-1 max-w-[220px]">{done.listing_title}</span>
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
  const subtotal = listing.price;
  const discount = coupon.discount || 0;
  const total = Math.max(0, subtotal + shippingFee - discount);
  const deliveryDays = publicSettings.delivery_days_estimate || 7;
  const eta = new Date(Date.now() + deliveryDays * 24 * 60 * 60 * 1000);
  const etaLabel = eta.toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <div className="max-w-5xl mx-auto px-4 py-8" data-testid="checkout-page">
      <div className="mb-8">
        <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
          {t("checkout.kicker")}
        </span>
        <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">{t("checkout.title")}</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{t("checkout.subtitle")}</p>
      </div>
      <form onSubmit={place} className="grid lg:grid-cols-[1fr_360px] gap-8">
        <div className="space-y-4">
          <section className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <div className="flex items-center justify-between mb-4">
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

          <section className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <div className="flex items-center gap-2 mb-4">
              <div className="h-8 w-8 rounded-lg bg-emerald-50 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 grid place-items-center">
                <Lock className="h-4 w-4" />
              </div>
              <h2 className="font-bold text-lg text-neutral-900 dark:text-neutral-100">{t("checkout.payment")}</h2>
              <span className="ml-auto text-[10px] uppercase tracking-wider font-semibold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 rounded-full px-2 py-0.5">
                {t("checkout.demo")}
              </span>
            </div>

            {/* Method selector — 4 vibrant chips */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5" data-testid="pay-method-selector">
              {[
                { id: "card",   icon: CreditCard, label: "Card",   tone: "from-sky-400 to-sky-600" },
                { id: "wallet", icon: WalletIcon, label: "Wallet", tone: "from-emerald-400 to-emerald-600" },
                { id: "crypto", icon: Bitcoin,    label: "Crypto", tone: "from-amber-400 to-orange-600" },
                { id: "bank",   icon: Building2,  label: "Bank",   tone: "from-purple-400 to-fuchsia-600" },
              ].map((m) => {
                const active = payMethod === m.id;
                const Icon = m.icon;
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setPayMethod(m.id)}
                    className={`min-h-[72px] rounded-2xl border-2 transition-all active:scale-95 hover:-translate-y-0.5 flex flex-col items-center justify-center gap-1.5 ${
                      active
                        ? "border-transparent bg-gradient-to-br " + m.tone + " text-white shadow-lg"
                        : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300 hover:border-neutral-400"
                    }`}
                    data-testid={`pay-method-${m.id}`}
                  >
                    <Icon className={`h-5 w-5 ${active ? "text-white" : "text-neutral-500"}`} />
                    <span className="text-sm font-semibold">{m.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Card fields */}
            {payMethod === "card" && (
              <div className="space-y-3 animate-in fade-in-50 duration-200" data-testid="pay-card-panel">
                <div><Label>{t("checkout.cardNumber")}</Label><Input value={card.number} onChange={(e) => setCard({ ...card, number: e.target.value })} className="mt-1 h-11 tabular-nums" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>{t("checkout.expiry")}</Label><Input value={card.exp} onChange={(e) => setCard({ ...card, exp: e.target.value })} className="mt-1 h-11 tabular-nums" /></div>
                  <div><Label>{t("checkout.cvc")}</Label><Input value={card.cvc} onChange={(e) => setCard({ ...card, cvc: e.target.value })} className="mt-1 h-11 tabular-nums" /></div>
                </div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400">{t("checkout.demoNote")}</p>
              </div>
            )}

            {/* Wallet balance */}
            {payMethod === "wallet" && (
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
                  <div className="mt-3 text-xs text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-lg px-3 py-2">
                    Insufficient balance. Please deposit or choose another method.
                  </div>
                ) : (
                  <p className="mt-3 text-[11px] text-emerald-700 dark:text-emerald-300">Order confirmation happens instantly with wallet payment.</p>
                )}
              </div>
            )}

            {/* Crypto: asset chips + network chips + QR + address */}
            {payMethod === "crypto" && (
              <div className="animate-in fade-in-50 duration-200 space-y-3" data-testid="pay-crypto-panel">
                {(payMethods.crypto_assets || []).length === 0 ? (
                  <div className="text-sm text-neutral-500 p-4 border border-dashed border-neutral-300 dark:border-neutral-700 rounded-xl">No crypto assets configured. Contact support.</div>
                ) : (() => {
                  const ASSET_BRAND = {
                    BTC:   { color: "from-orange-400 to-amber-600",   text: "text-white" },
                    ETH:   { color: "from-indigo-400 to-indigo-700",  text: "text-white" },
                    SOL:   { color: "from-purple-500 to-fuchsia-600", text: "text-white" },
                    BNB:   { color: "from-yellow-400 to-amber-500",   text: "text-neutral-900" },
                    USDC:  { color: "from-sky-400 to-blue-600",       text: "text-white" },
                    USDT:  { color: "from-teal-400 to-emerald-600",   text: "text-white" },
                    MATIC: { color: "from-violet-500 to-purple-700",  text: "text-white" },
                  };
                  const NETWORK_BADGE = {
                    Bitcoin:  "bg-amber-100 text-amber-800 border-amber-300",
                    Ethereum: "bg-indigo-100 text-indigo-800 border-indigo-300",
                    Solana:   "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-300",
                    "BEP-20": "bg-yellow-100 text-yellow-800 border-yellow-300",
                    Polygon:  "bg-violet-100 text-violet-800 border-violet-300",
                  };
                  const symbols = Array.from(new Set(payMethods.crypto_assets.map((a) => a.symbol)));
                  const currentSymbol = (payMethods.crypto_assets.find((a) => a.id === assetId) || {}).symbol;
                  const symbolAssets = payMethods.crypto_assets.filter((a) => a.symbol === currentSymbol);
                  const selected = payMethods.crypto_assets.find((a) => a.id === assetId);
                  return (
                    <>
                      <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Asset</div>
                      <div className="flex gap-2 flex-wrap" data-testid="crypto-asset-chips">
                        {symbols.map((sym) => {
                          const first = payMethods.crypto_assets.find((a) => a.symbol === sym);
                          const isActive = currentSymbol === sym;
                          const brand = ASSET_BRAND[sym] || { color: "from-neutral-500 to-neutral-700", text: "text-white" };
                          return (
                            <button
                              key={sym}
                              type="button"
                              onClick={() => setAssetId(first.id)}
                              className={`min-h-[44px] px-4 rounded-2xl font-bold text-sm border-2 transition-all active:scale-95 hover:-translate-y-0.5 ${isActive ? `bg-gradient-to-br ${brand.color} ${brand.text} border-transparent shadow-lg` : "bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:border-neutral-400"}`}
                              data-testid={`crypto-asset-${sym}`}
                            >{sym}</button>
                          );
                        })}
                      </div>

                      {symbolAssets.length > 0 && (
                        <>
                          <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold mt-2">Network</div>
                          <div className="flex gap-2 flex-wrap" data-testid="crypto-network-chips">
                            {symbolAssets.map((a) => {
                              const active = a.id === assetId;
                              const netCls = NETWORK_BADGE[a.network] || "bg-neutral-100 text-neutral-700 border-neutral-300";
                              return (
                                <button
                                  key={a.id}
                                  type="button"
                                  onClick={() => setAssetId(a.id)}
                                  className={`min-h-[36px] px-3 rounded-full text-xs font-semibold border transition-all active:scale-95 ${active ? `${netCls} ring-2 ring-offset-1 ring-current` : `${netCls} opacity-70 hover:opacity-100`}`}
                                  data-testid={`crypto-network-${a.id}`}
                                >{a.network}</button>
                              );
                            })}
                          </div>
                        </>
                      )}

                      {selected && selected.address && (
                        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 p-4 flex flex-col sm:flex-row gap-4 items-center sm:items-start" data-testid="crypto-detail-card">
                          <img src={qrUrl(selected.address)} alt={`${selected.symbol} QR`} className="rounded-lg bg-white p-2 h-40 w-40 shrink-0" data-testid="crypto-qr" />
                          <div className="min-w-0 flex-1 w-full space-y-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-lg font-extrabold">{selected.symbol}</span>
                              <span className={`text-[10px] uppercase font-semibold border rounded-full px-2 py-0.5 ${NETWORK_BADGE[selected.network] || "bg-neutral-100 text-neutral-700 border-neutral-300"}`}>
                                {selected.network}
                              </span>
                            </div>
                            <div className="font-mono text-xs break-all bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-2.5" data-testid="crypto-address">
                              {selected.address}
                            </div>
                            <button
                              type="button"
                              onClick={() => doCopy(selected.address, "crypto")}
                              className="min-h-[44px] px-3 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-[#FF211F] hover:text-[#FF211F] active:scale-95 transition-all flex items-center gap-1.5 text-sm font-medium"
                              data-testid="crypto-copy"
                            >
                              {copied === "crypto" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              {copied === "crypto" ? "Copied" : "Copy address"}
                            </button>
                            <p className="text-[11px] text-neutral-500">Send exactly <b>{format(total)}</b> worth of <b>{selected.symbol}</b> on <b>{selected.network}</b>. Wrong network = lost funds.</p>
                          </div>
                        </div>
                      )}
                      {selected && !selected.address && (
                        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">Address not configured for {selected.symbol} on {selected.network}. Pick another network.</div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}

            {/* Bank / manual instructions */}
            {payMethod === "bank" && (
              <div className="animate-in fade-in-50 duration-200 space-y-3" data-testid="pay-bank-panel">
                {(payMethods.manual_payment_methods || []).length === 0 ? (
                  <div className="text-sm text-neutral-500 p-4 border border-dashed border-neutral-300 dark:border-neutral-700 rounded-xl">No manual methods configured.</div>
                ) : (
                  <>
                    <div className="flex gap-2 flex-wrap">
                      {payMethods.manual_payment_methods.map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => setBankId(m.id)}
                          className={`min-h-[36px] px-3 rounded-full text-xs font-bold border transition-all active:scale-95 ${bankId === m.id ? "bg-gradient-to-br from-purple-400 to-fuchsia-600 text-white border-transparent shadow-md" : "border-neutral-200 dark:border-neutral-700 hover:border-fuchsia-400"}`}
                          data-testid={`bank-method-${m.id}`}
                        >{m.name}</button>
                      ))}
                    </div>
                    {bankId && (() => {
                      const m = payMethods.manual_payment_methods.find((x) => x.id === bankId);
                      if (!m) return null;
                      return (
                        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 p-4" data-testid="bank-instructions">
                          <div className="text-xs uppercase tracking-wider text-neutral-500 font-semibold mb-2">Instructions</div>
                          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed break-words text-neutral-800 dark:text-neutral-200">{m.instructions || "No instructions provided."}</pre>
                          {m.instructions && (
                            <button
                              type="button"
                              onClick={() => doCopy(m.instructions, "bank")}
                              className="mt-3 min-h-[44px] px-3 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-[#FF211F] hover:text-[#FF211F] active:scale-95 transition-all flex items-center gap-1.5 text-sm font-medium"
                              data-testid="bank-copy"
                            >
                              {copied === "bank" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              {copied === "bank" ? "Copied" : "Copy details"}
                            </button>
                          )}
                          <p className="text-[11px] text-neutral-500 mt-2">Complete the transfer and place the order. Your order goes on hold until admin confirms.</p>
                        </div>
                      );
                    })()}
                  </>
                )}
              </div>
            )}
          </section>
        </div>

        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 h-fit lg:sticky lg:top-24 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
          <h2 className="font-bold text-lg mb-4 text-neutral-900 dark:text-neutral-100">{t("cart.orderSummary")}</h2>
          <div className="flex gap-3 mb-4 pb-4 border-b border-neutral-100 dark:border-neutral-800">
            <img src={listing.images?.[0]} alt="" className="h-16 w-16 rounded-xl object-cover ring-1 ring-black/[0.04] dark:ring-white/10" />
            <div className="text-sm min-w-0">
              <div className="font-semibold line-clamp-2 text-neutral-900 dark:text-neutral-100">{listing.title}</div>
              <div className="text-neutral-500 dark:text-neutral-400 text-xs mt-0.5">{t("cart.soldBy")} {listing.seller_name}</div>
            </div>
          </div>
          <div className="space-y-2.5 text-sm">
            <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
              <span>{t("checkout.item")}</span>
              <span className="tabular-nums font-medium">{format(listing.price)}</span>
            </div>
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
            disabled={placing || (payMethod === "wallet" && wallet && (wallet.balance ?? 0) < total)}
            className="w-full mt-5 bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 rounded-full h-12 min-h-[48px] font-bold shadow-lg shadow-[#FF211F]/30 disabled:opacity-60 hover:-translate-y-0.5 active:translate-y-0 transition-all hidden lg:block"
            data-testid="place-order-btn"
          >
            {placing ? t("checkout.placing") : `${t("checkout.pay")} ${format(total)}`}
          </Button>
        </div>
      </form>

      {/* Sticky mobile action bar — visible only on <lg screens */}
      <div
        className="lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-neutral-200 dark:border-neutral-800 bg-white/95 dark:bg-neutral-950/95 backdrop-blur px-4 py-3 flex items-center justify-between gap-3 shadow-[0_-4px_16px_rgba(0,0,0,0.08)]"
        data-testid="sticky-checkout-bar"
      >
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-widest text-neutral-500 dark:text-neutral-400">{t("cart.total")}</div>
          <div className="text-lg font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(total)}</div>
        </div>
        <Button
          type="button"
          onClick={place}
          disabled={placing || (payMethod === "wallet" && wallet && (wallet.balance ?? 0) < total)}
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
