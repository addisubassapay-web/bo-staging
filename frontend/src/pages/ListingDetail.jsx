import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api, { formatPrice, conditionLabel } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Heart, ShoppingCart, MessageCircle, Truck, Shield, ChevronLeft, Share2, Star, LinkIcon, Copy, PackagePlus } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ListingReviews } from "@/components/Reviews";
import { VerificationBadges } from "@/components/VerificationBadges";
import ProductCard from "@/components/ProductCard";
import SimilarItems from "@/components/SimilarItems";

const SellerBlock = ({ sellerId, sellerName, views }) => {
  const [seller, setSeller] = useState(null);
  useEffect(() => {
    if (!sellerId) return;
    api.get(`/users/${sellerId}/public`).then((r) => setSeller(r.data)).catch(() => {});
  }, [sellerId]);
  return (
    <div className="flex items-start gap-3" data-testid="seller-block">
      <div className="h-11 w-11 rounded-full bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center font-bold shadow-sm shrink-0">
        {sellerName?.[0]?.toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-neutral-900 dark:text-neutral-100">{sellerName}</span>
          {seller && <VerificationBadges user={seller} showLabels={false} />}
        </div>
        <div className="text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-2 mt-0.5">
          {seller && <span className="flex items-center gap-0.5"><Star className="h-3 w-3 fill-yellow-400 text-yellow-400" /> {seller.rating}</span>}
          {seller && <span>· {seller.sales_count} sales</span>}
          <span>· {views} views</span>
        </div>
      </div>
    </div>
  );
};

const AffiliateShareButton = ({ listingId }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);

  const create = async () => {
    if (!user) { navigate("/login"); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/affiliate/links", { listing_id: listingId });
      setLink(`${window.location.origin}/r/${data.code}`);
      setOpen(true);
    } catch {
      toast({ title: "Failed to create link", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    navigator.clipboard.writeText(link);
    toast({ title: "Link copied" });
  };

  return (
    <>
      <Button onClick={create} variant="outline" className="h-11" disabled={loading}>
        <LinkIcon className="h-4 w-4 mr-2" /> Share as affiliate
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Your affiliate link</DialogTitle></DialogHeader>
          <p className="text-sm text-neutral-600">Share this link. You&apos;ll earn a commission on every sale.</p>
          <div className="flex gap-2 mt-2">
            <Input value={link} readOnly className="font-mono text-xs" />
            <Button onClick={copy}><Copy className="h-4 w-4" /></Button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
            <Button className="bg-[#FF211F] hover:bg-[#e01d1b]" onClick={() => navigate("/affiliate")}>Go to dashboard</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

const DropshipImportButton = ({ listing, onImported }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [markup, setMarkup] = useState(20);
  const [loading, setLoading] = useState(false);

  const doImport = async () => {
    if (!user) { navigate("/login"); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/listings/import", { listing_id: listing.id, markup_pct: parseFloat(markup) });
      toast({ title: "Imported to your store", description: "You'll earn the markup on every sale." });
      setOpen(false);
      onImported?.(data.id);
    } catch (err) {
      toast({ title: "Import failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const newPrice = (listing.price * (1 + markup / 100)).toFixed(2);
  const earn = (listing.price * markup / 100).toFixed(2);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className="h-11">
          <PackagePlus className="h-4 w-4 mr-2" /> Import & resell
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Import to your store</DialogTitle></DialogHeader>
        <p className="text-sm text-neutral-600">
          Sell this item without holding inventory. Set your markup — you earn the difference, the original seller fulfills.
        </p>
        <div className="mt-3">
          <Label>Markup %</Label>
          <Input type="number" min="0" max="100" value={markup} onChange={(e) => setMarkup(e.target.value)} className="mt-1" />
        </div>
        <div className="mt-3 bg-neutral-50 rounded-lg p-3 text-sm space-y-1">
          <div className="flex justify-between"><span>Base price</span><span>${listing.price.toFixed(2)}</span></div>
          <div className="flex justify-between"><span>Your listing price</span><span className="font-semibold">${newPrice}</span></div>
          <div className="flex justify-between text-green-600"><span>You earn per sale</span><span className="font-semibold">${earn}</span></div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="button" className="bg-[#FF211F] hover:bg-[#e01d1b]" onClick={doImport} disabled={loading}>
            {loading ? "Importing…" : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ListingDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { toast } = useToast();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeImg, setActiveImg] = useState(0);
  const [fav, setFav] = useState(false);
  const [inCart, setInCart] = useState(false);
  const [bundle, setBundle] = useState([]);

  const load = () => {
    setLoading(true);
    api.get(`/listings/${id}`)
      .then((r) => setListing(r.data))
      .catch(() => toast({ title: "Listing not found", variant: "destructive" }))
      .finally(() => setLoading(false));
    api.get(`/listings/${id}/bundle`, { params: { limit: 6 } }).then((r) => setBundle(r.data)).catch(() => setBundle([]));
  };

  useEffect(() => {
    load();
    setActiveImg(0);
    if (user) {
      api.get("/favorites").then((r) => setFav(r.data.some((l) => l.id === id))).catch(() => {});
      api.get("/cart").then((r) => setInCart(r.data.some((l) => l.id === id))).catch(() => {});
      api.post(`/recently-viewed/${id}`).catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, user]);

  const requireAuth = () => {
    if (!user) {
      toast({ title: "Please log in to continue" });
      navigate("/login");
      return false;
    }
    return true;
  };

  const toggleFav = async () => {
    if (!requireAuth()) return;
    try {
      if (fav) {
        await api.delete(`/favorites/${id}`);
        setFav(false);
      } else {
        await api.post(`/favorites/${id}`);
        setFav(true);
      }
    } catch {
      toast({ title: "Something went wrong", variant: "destructive" });
    }
  };

  const addToCart = async () => {
    if (!requireAuth()) return;
    try {
      await api.post(`/cart/${id}`);
      setInCart(true);
      toast({ title: "Added to cart" });
    } catch {
      toast({ title: "Could not add to cart", variant: "destructive" });
    }
  };

  const buyNow = () => {
    if (!requireAuth()) return;
    navigate(`/checkout/${id}`);
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 grid md:grid-cols-2 gap-8">
        <div className="aspect-square bg-neutral-100 rounded-lg animate-pulse" />
        <div className="space-y-4">
          <div className="h-8 bg-neutral-100 rounded animate-pulse" />
          <div className="h-6 bg-neutral-100 rounded animate-pulse w-1/3" />
          <div className="h-24 bg-neutral-100 rounded animate-pulse" />
        </div>
      </div>
    );
  }

  if (!listing) return null;

  const isOwn = user && user.id === listing.seller_id;
  const isSold = listing.status === "sold";

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-neutral-600 dark:text-neutral-400 mb-5 hover:text-neutral-900 dark:hover:text-neutral-100 transition">
        <ChevronLeft className="h-4 w-4" /> Back
      </button>

      <div className="grid md:grid-cols-2 gap-8 lg:gap-12">
        {/* Gallery */}
        <div>
          <div className="relative aspect-square rounded-2xl overflow-hidden bg-neutral-100 dark:bg-neutral-800 ring-1 ring-black/[0.04] dark:ring-white/10 shadow-[0_4px_20px_-8px_rgba(0,0,0,0.15)]">
            <img src={listing.images?.[activeImg]} alt={listing.title} className="w-full h-full object-cover" />
            {isSold && (
              <div className="absolute inset-0 bg-gradient-to-br from-black/70 via-black/45 to-black/30 grid place-items-center backdrop-blur-[1px]">
                <span className="bg-white text-neutral-900 font-bold tracking-wide px-4 py-1.5 rounded-full text-sm shadow-lg uppercase">Sold</span>
              </div>
            )}
          </div>
          {listing.images?.length > 1 && (
            <div className="grid grid-cols-5 gap-2 mt-3">
              {listing.images.map((img, i) => (
                <button
                  key={i}
                  onClick={() => setActiveImg(i)}
                  className={`aspect-square rounded-xl overflow-hidden ring-2 transition ${activeImg === i ? "ring-[#FF211F] ring-offset-2 ring-offset-white dark:ring-offset-neutral-950" : "ring-transparent hover:ring-neutral-200 dark:hover:ring-neutral-700"}`}
                >
                  <img src={img} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Info column */}
        <div>
          <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
            {listing.category_name}
          </span>
          <div className="mt-2 flex items-start justify-between gap-4">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">{listing.title}</h1>
            <button
              onClick={() => { navigator.clipboard.writeText(window.location.href); toast({ title: "Link copied" }); }}
              className="h-10 w-10 rounded-full grid place-items-center border border-neutral-200 dark:border-neutral-800 text-neutral-500 dark:text-neutral-300 hover:text-[#FF211F] hover:border-[#FF7A18] transition shrink-0"
              aria-label="Share"
              data-testid="share-btn"
            >
              <Share2 className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-3 flex items-baseline gap-3">
            <span className="text-4xl font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{formatPrice(listing.price)}</span>
            {listing.original_price && listing.original_price > listing.price && (
              <>
                <span className="text-neutral-400 dark:text-neutral-500 line-through tabular-nums">{formatPrice(listing.original_price)}</span>
                <span className="text-xs font-bold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 rounded-full px-2 py-0.5">
                  -{Math.round((1 - listing.price / listing.original_price) * 100)}% off
                </span>
              </>
            )}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant="secondary" className="rounded-full">{conditionLabel(listing.condition)}</Badge>
            {listing.brand && <Badge variant="secondary" className="rounded-full">{listing.brand}</Badge>}
            {listing.size && <Badge variant="secondary" className="rounded-full">Size {listing.size}</Badge>}
            {listing.color && <Badge variant="secondary" className="rounded-full">{listing.color}</Badge>}
          </div>

          <div className="mt-5 grid sm:grid-cols-2 gap-2 text-sm">
            <div className="flex items-center gap-2 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-3 py-2">
              <div className="h-7 w-7 rounded-lg bg-sky-50 dark:bg-sky-500/15 text-sky-600 dark:text-sky-300 grid place-items-center"><Truck className="h-3.5 w-3.5" /></div>
              <span className="text-neutral-700 dark:text-neutral-300">{listing.shipping_paid_by === "seller" ? "Free shipping" : "Buyer pays shipping"}</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-3 py-2">
              <div className="h-7 w-7 rounded-lg bg-emerald-50 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 grid place-items-center"><Shield className="h-3.5 w-3.5" /></div>
              <span className="text-neutral-700 dark:text-neutral-300">Buyer Protection</span>
            </div>
          </div>

          {!isOwn && !isSold && (
            <div className="mt-6 space-y-2.5">
              <Button
                onClick={buyNow}
                className="w-full h-12 bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-105 text-white text-base font-bold rounded-full shadow-lg shadow-[#FF211F]/25"
                data-testid="buy-now-btn"
              >
                Buy now · {formatPrice(listing.price)}
              </Button>
              <div className="grid grid-cols-2 gap-2">
                <Button onClick={addToCart} variant="outline" className="h-11 rounded-full" disabled={inCart} data-testid="add-to-cart-btn">
                  <ShoppingCart className="h-4 w-4 mr-2" /> {inCart ? "In cart" : "Add to cart"}
                </Button>
                <Button onClick={toggleFav} variant="outline" className="h-11 rounded-full" data-testid="fav-toggle-btn">
                  <Heart className={`h-4 w-4 mr-2 ${fav ? "fill-[#FF211F] text-[#FF211F]" : ""}`} />
                  {fav ? "Saved" : "Save"}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <AffiliateShareButton listingId={listing.id} />
                <DropshipImportButton listing={listing} onImported={(id) => navigate(`/listing/${id}`)} />
              </div>
              <Button variant="ghost" className="w-full h-11 rounded-full" onClick={() => { if (!user) { navigate("/login"); return; } navigate(`/chat/${listing.id}/${listing.seller_id}`); }}>
                <MessageCircle className="h-4 w-4 mr-2" /> Message seller
              </Button>
            </div>
          )}
          {isOwn && (
            <div className="mt-6 p-4 rounded-2xl bg-orange-50 dark:bg-[#FF7A18]/10 border border-orange-200 dark:border-orange-500/30 text-sm text-neutral-700 dark:text-neutral-200">
              This is your listing. Manage it from your <Link to="/profile?tab=listings" className="text-[#FF211F] font-semibold hover:underline">profile</Link>.
            </div>
          )}
          {isSold && !isOwn && (
            <div className="mt-6 p-4 rounded-2xl bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-sm text-neutral-600 dark:text-neutral-300">
              This item has been sold.
            </div>
          )}

          <div className="mt-8 border-t border-neutral-200 dark:border-neutral-800 pt-6">
            <h2 className="font-bold text-neutral-900 dark:text-neutral-100 mb-2">Description</h2>
            <p className="text-neutral-700 dark:text-neutral-300 whitespace-pre-line leading-relaxed">{listing.description}</p>
          </div>

          <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <SellerBlock sellerId={listing.seller_id} sellerName={listing.seller_name} views={listing.views_count} />
          </div>

          <ListingReviews listingId={listing.id} />
        </div>
      </div>

      {/* You may also like */}
      <SimilarItems listingId={listing.id} />

      {/* Smart Bundles */}
      {bundle.length > 0 && (
        <div className="mt-16 sm:mt-20" data-testid="bundles-section">
          <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
            Bundle & save
          </span>
          <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">Complete the look</h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">More from this seller — bundle up and save on shipping.</p>
          <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
            {bundle.map((l) => (
              <ProductCard key={l.id} listing={l} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ListingDetail;
