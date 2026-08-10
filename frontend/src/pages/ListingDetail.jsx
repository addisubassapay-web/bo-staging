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

const SellerBlock = ({ sellerId, sellerName, views }) => {
  const [seller, setSeller] = useState(null);
  useEffect(() => {
    if (!sellerId) return;
    api.get(`/users/${sellerId}/public`).then((r) => setSeller(r.data)).catch(() => {});
  }, [sellerId]);
  return (
    <div className="flex items-start gap-3" data-testid="seller-block">
      <div className="h-11 w-11 rounded-full bg-neutral-200 grid place-items-center font-semibold text-neutral-700">
        {sellerName?.[0]?.toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-neutral-900">{sellerName}</span>
          {seller && <VerificationBadges user={seller} showLabels={false} />}
        </div>
        <div className="text-xs text-neutral-500 flex items-center gap-2 mt-0.5">
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

  const load = () => {
    setLoading(true);
    api.get(`/listings/${id}`)
      .then((r) => setListing(r.data))
      .catch(() => toast({ title: "Listing not found", variant: "destructive" }))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    setActiveImg(0);
    if (user) {
      api.get("/favorites").then((r) => setFav(r.data.some((l) => l.id === id))).catch(() => {});
      api.get("/cart").then((r) => setInCart(r.data.some((l) => l.id === id))).catch(() => {});
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
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-neutral-600 mb-4 hover:text-neutral-900">
        <ChevronLeft className="h-4 w-4" /> Back
      </button>

      <div className="grid md:grid-cols-2 gap-8">
        <div>
          <div className="relative aspect-square rounded-lg overflow-hidden bg-neutral-100">
            <img src={listing.images?.[activeImg]} alt={listing.title} className="w-full h-full object-cover" />
            {isSold && (
              <div className="absolute inset-0 bg-black/50 grid place-items-center">
                <span className="bg-white text-neutral-900 font-bold px-4 py-2 rounded">SOLD</span>
              </div>
            )}
          </div>
          {listing.images?.length > 1 && (
            <div className="grid grid-cols-5 gap-2 mt-3">
              {listing.images.map((img, i) => (
                <button
                  key={i}
                  onClick={() => setActiveImg(i)}
                  className={`aspect-square rounded overflow-hidden border-2 ${activeImg === i ? "border-[#FF211F]" : "border-transparent"}`}
                >
                  <img src={img} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-2xl font-bold text-neutral-900">{listing.title}</h1>
            <button onClick={() => { navigator.clipboard.writeText(window.location.href); toast({ title: "Link copied" }); }} className="text-neutral-500 hover:text-neutral-900">
              <Share2 className="h-5 w-5" />
            </button>
          </div>

          <div className="mt-3 flex items-baseline gap-3">
            <span className="text-3xl font-bold text-neutral-900">{formatPrice(listing.price)}</span>
            {listing.original_price && listing.original_price > listing.price && (
              <span className="text-neutral-400 line-through">{formatPrice(listing.original_price)}</span>
            )}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant="secondary">{conditionLabel(listing.condition)}</Badge>
            <Badge variant="secondary">{listing.category_name}</Badge>
            {listing.brand && <Badge variant="secondary">{listing.brand}</Badge>}
            {listing.size && <Badge variant="secondary">Size {listing.size}</Badge>}
            {listing.color && <Badge variant="secondary">{listing.color}</Badge>}
          </div>

          <div className="mt-5 space-y-2 text-sm text-neutral-700">
            <div className="flex items-center gap-2">
              <Truck className="h-4 w-4 text-neutral-500" />
              {listing.shipping_paid_by === "seller" ? "Free shipping" : "Buyer pays shipping"} · {listing.shipping_method}
            </div>
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-neutral-500" />
              Protected by Mercari Buyer Protection
            </div>
          </div>

          {!isOwn && !isSold && (
            <div className="mt-6 space-y-2">
              <Button onClick={buyNow} className="w-full h-12 bg-[#FF211F] hover:bg-[#e01d1b] text-base font-semibold">Buy now</Button>
              <div className="grid grid-cols-2 gap-2">
                <Button onClick={addToCart} variant="outline" className="h-11" disabled={inCart}>
                  <ShoppingCart className="h-4 w-4 mr-2" /> {inCart ? "In cart" : "Add to cart"}
                </Button>
                <Button onClick={toggleFav} variant="outline" className="h-11">
                  <Heart className={`h-4 w-4 mr-2 ${fav ? "fill-[#FF211F] text-[#FF211F]" : ""}`} />
                  {fav ? "Saved" : "Save"}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <AffiliateShareButton listingId={listing.id} />
                <DropshipImportButton listing={listing} onImported={(id) => navigate(`/listing/${id}`)} />
              </div>
              <Button variant="ghost" className="w-full h-11" onClick={() => { if (!user) { navigate("/login"); return; } navigate(`/chat/${listing.id}/${listing.seller_id}`); }}>
                <MessageCircle className="h-4 w-4 mr-2" /> Message seller
              </Button>
            </div>
          )}
          {isOwn && (
            <div className="mt-6 p-4 bg-neutral-50 border border-neutral-200 rounded-lg text-sm">
              This is your listing. Manage it from your <Link to="/profile?tab=listings" className="text-[#FF211F] font-medium hover:underline">profile</Link>.
            </div>
          )}
          {isSold && !isOwn && (
            <div className="mt-6 p-4 bg-neutral-100 border border-neutral-200 rounded-lg text-sm text-neutral-600">
              This item has been sold.
            </div>
          )}

          <div className="mt-8 border-t pt-6">
            <h2 className="font-semibold text-neutral-900 mb-2">Description</h2>
            <p className="text-neutral-700 whitespace-pre-line leading-relaxed">{listing.description}</p>
          </div>

          <div className="mt-6 border-t pt-6">
            <SellerBlock sellerId={listing.seller_id} sellerName={listing.seller_name} views={listing.views_count} />
          </div>

          <ListingReviews listingId={listing.id} />
        </div>
      </div>
    </div>
  );
};

export default ListingDetail;
