import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { CheckCircle2, Lock, Share2 } from "lucide-react";
import confetti from "canvas-confetti";

const Checkout = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const [listing, setListing] = useState(null);
  const [address, setAddress] = useState({ full_name: "", street: "", city: "", state: "", zip: "", country: "USA" });
  const [card, setCard] = useState({ number: "4242 4242 4242 4242", exp: "12/28", cvc: "123" });
  const [placing, setPlacing] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get(`/listings/${id}`).then((r) => setListing(r.data));
  }, [id, user, authLoading, navigate]);

  const place = async (e) => {
    e.preventDefault();
    if (!address.full_name || !address.street || !address.city || !address.zip) {
      toast({ title: "Please complete your shipping address", variant: "destructive" });
      return;
    }
    setPlacing(true);
    try {
      const affiliate_code = sessionStorage.getItem("affiliate_code") || null;
      const { data } = await api.post("/orders", { listing_id: id, shipping_address: address, affiliate_code });
      setDone(data);
      sessionStorage.removeItem("affiliate_code");
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
      toast({ title: "Payment failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
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
          toast({ title: "Copied to clipboard", description: "Share your win with friends!" });
        } catch { /* ignore */ }
      }
    };
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center" data-testid="checkout-success">
        <div className="relative inline-block">
          <CheckCircle2 className="h-16 w-16 mx-auto text-green-500" />
          <span className="absolute -top-1 -right-1 text-2xl">🎉</span>
        </div>
        <h1 className="text-3xl font-bold mt-4">Score! Order placed</h1>
        <p className="text-neutral-600 mt-2">We&apos;ve notified {done.seller_name}. You&apos;ll get updates as your item ships.</p>
        <div className="mt-6 bg-neutral-50 rounded-lg p-4 text-left text-sm">
          <div className="flex justify-between"><span>Order ID</span><span className="font-mono">{done.id.slice(0, 8)}</span></div>
          <div className="flex justify-between mt-1"><span>Item</span><span>{done.listing_title}</span></div>
          <div className="flex justify-between mt-1"><span>Amount</span><span className="font-semibold">{formatPrice(done.amount + done.shipping_fee)}</span></div>
        </div>
        <div className="mt-6 flex gap-2 justify-center flex-wrap">
          <Button variant="outline" onClick={doShare} className="gap-1.5" data-testid="checkout-share-btn">
            <Share2 className="h-4 w-4" /> Share your win
          </Button>
          <Button variant="outline" onClick={() => navigate("/profile?tab=orders")}>View orders</Button>
          <Button className="bg-[#FF211F] hover:bg-[#e01d1b]" onClick={() => navigate("/")}>Keep shopping</Button>
        </div>
      </div>
    );
  }

  const shippingFee = listing.shipping_paid_by === "buyer" ? 5.99 : 0;
  const total = listing.price + shippingFee;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Checkout</h1>
      <form onSubmit={place} className="grid lg:grid-cols-[1fr_360px] gap-8">
        <div className="space-y-6">
          <section className="border border-neutral-200 rounded-lg p-5">
            <h2 className="font-semibold mb-4">Shipping address</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2"><Label>Full name</Label><Input value={address.full_name} onChange={(e) => setAddress({ ...address, full_name: e.target.value })} required className="mt-1" /></div>
              <div className="sm:col-span-2"><Label>Street address</Label><Input value={address.street} onChange={(e) => setAddress({ ...address, street: e.target.value })} required className="mt-1" /></div>
              <div><Label>City</Label><Input value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} required className="mt-1" /></div>
              <div><Label>State</Label><Input value={address.state} onChange={(e) => setAddress({ ...address, state: e.target.value })} required className="mt-1" /></div>
              <div><Label>ZIP</Label><Input value={address.zip} onChange={(e) => setAddress({ ...address, zip: e.target.value })} required className="mt-1" /></div>
              <div><Label>Country</Label><Input value={address.country} onChange={(e) => setAddress({ ...address, country: e.target.value })} className="mt-1" /></div>
            </div>
          </section>

          <section className="border border-neutral-200 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-4">
              <Lock className="h-4 w-4 text-neutral-500" />
              <h2 className="font-semibold">Payment (demo)</h2>
            </div>
            <div className="space-y-3">
              <div><Label>Card number</Label><Input value={card.number} onChange={(e) => setCard({ ...card, number: e.target.value })} className="mt-1" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Expiry</Label><Input value={card.exp} onChange={(e) => setCard({ ...card, exp: e.target.value })} className="mt-1" /></div>
                <div><Label>CVC</Label><Input value={card.cvc} onChange={(e) => setCard({ ...card, cvc: e.target.value })} className="mt-1" /></div>
              </div>
              <p className="text-xs text-neutral-500">This is a demo. No real payment is processed.</p>
            </div>
          </section>
        </div>

        <div className="border border-neutral-200 rounded-lg p-5 h-fit sticky top-20">
          <h2 className="font-semibold mb-4">Order summary</h2>
          <div className="flex gap-3 mb-4">
            <img src={listing.images?.[0]} alt="" className="h-16 w-16 rounded object-cover" />
            <div className="text-sm">
              <div className="font-medium line-clamp-2">{listing.title}</div>
              <div className="text-neutral-500 text-xs">by {listing.seller_name}</div>
            </div>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span>Item</span><span>{formatPrice(listing.price)}</span></div>
            <div className="flex justify-between"><span>Shipping</span><span>{formatPrice(shippingFee)}</span></div>
            <div className="h-px bg-neutral-200 my-2" />
            <div className="flex justify-between font-semibold text-base"><span>Total</span><span>{formatPrice(total)}</span></div>
          </div>
          <Button type="submit" disabled={placing} className="w-full mt-4 bg-[#FF211F] hover:bg-[#e01d1b] h-11">
            {placing ? "Placing order…" : `Pay ${formatPrice(total)}`}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default Checkout;
