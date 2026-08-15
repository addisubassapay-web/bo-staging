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
import { CheckCircle2, Lock, Share2 } from "lucide-react";
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

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get(`/listings/${id}`).then((r) => setListing(r.data));
    api.get("/settings/public").then((r) => setPublicSettings(r.data)).catch(() => {});
  }, [id, user, authLoading, navigate]);

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
      const { data } = await api.post("/orders", { listing_id: id, shipping_address: address, affiliate_code, share_ref });
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
  const total = listing.price + shippingFee;
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
            <h2 className="font-bold text-lg mb-4 text-neutral-900 dark:text-neutral-100">{t("checkout.shippingAddress")}</h2>
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
            <div className="space-y-3">
              <div><Label>{t("checkout.cardNumber")}</Label><Input value={card.number} onChange={(e) => setCard({ ...card, number: e.target.value })} className="mt-1 tabular-nums" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>{t("checkout.expiry")}</Label><Input value={card.exp} onChange={(e) => setCard({ ...card, exp: e.target.value })} className="mt-1 tabular-nums" /></div>
                <div><Label>{t("checkout.cvc")}</Label><Input value={card.cvc} onChange={(e) => setCard({ ...card, cvc: e.target.value })} className="mt-1 tabular-nums" /></div>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">{t("checkout.demoNote")}</p>
            </div>
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
            disabled={placing}
            className="w-full mt-5 bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-11 shadow-lg shadow-[#FF211F]/20 disabled:opacity-60"
            data-testid="place-order-btn"
          >
            {placing ? t("checkout.placing") : `${t("checkout.pay")} ${format(total)}`}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default Checkout;
