import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link, useSearchParams } from "react-router-dom";
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
import { flagEmoji, countryName } from "@/constants/countries";
import ProductCard from "@/components/ProductCard";
import SimilarItems from "@/components/SimilarItems";
import StorefrontShareButton from "@/components/StorefrontShare";
import { useLang } from "@/context/LanguageContext";

const SellerBlock = ({ sellerId, sellerName, sellerCountry, views }) => {
  const [seller, setSeller] = useState(null);
  useEffect(() => {
    if (!sellerId) return;
    api.get(`/users/${sellerId}/public`).then((r) => setSeller(r.data)).catch(() => {});
  }, [sellerId]);
  // Fall back to the listing's own country when the fresher public-user
  // record doesn't carry one; on the storefront this covers BlueOcean
  // Store dropship items (seller country lives on the listing, not the user).
  const country = seller?.country || sellerCountry;
  return (
    <div className="flex items-start gap-3" data-testid="seller-block">
      <div className="h-11 w-11 rounded-full bg-gradient-to-br from-[#1E40AF] to-[#3B82F6] text-white grid place-items-center font-bold shadow-sm shrink-0">
        {sellerName?.[0]?.toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-neutral-900 dark:text-neutral-100">{sellerName}</span>
          {country && flagEmoji(country) && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 text-[11px] font-medium text-neutral-700 dark:text-neutral-200"
              title={`Ships from ${countryName(country)}`}
              data-testid="seller-country-badge"
            >
              <span aria-hidden="true">{flagEmoji(country)}</span>
              {countryName(country)}
            </span>
          )}
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
            <Button className="bg-[#DC2626] hover:bg-[#e01d1b]" onClick={() => navigate("/affiliate")}>Go to dashboard</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

const DropshipRowLine = ({ label, value, tone = "" }) => (
  <div className="flex justify-between items-center text-sm">
    <span className="text-neutral-600 dark:text-neutral-300">{label}</span>
    <span className={`tabular-nums font-medium ${tone}`}>{value}</span>
  </div>
);

const DropshipImportButton = ({ listing, onImported }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [markup, setMarkup] = useState(20);
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState({ platform_fee_pct: 8, dropship_max_markup_pct: 100 });

  useEffect(() => {
    if (!open) return;
    api.get("/settings/public").then((r) => setSettings((s) => ({ ...s, ...r.data }))).catch(() => {});
    api.get("/admin/settings").then((r) => setSettings((s) => ({ ...s, ...r.data }))).catch(() => {}); // admins get extra fields; others silently fail
  }, [open]);

  const markupNum = Math.max(0, Number(markup) || 0);
  const basePrice = Number(listing.price) || 0;
  const salePrice = +(basePrice * (1 + markupNum / 100)).toFixed(2);
  const platformFeePct = Number(settings.platform_fee_pct ?? 8);
  const maxMarkup = Number(settings.dropship_max_markup_pct ?? 100);
  const platformFee = +(salePrice * platformFeePct / 100).toFixed(2);
  const sourceEarnings = basePrice; // seller of original listing always keeps base_price on dropship sales
  const resellerEarnings = Math.max(0, +(salePrice - platformFee - sourceEarnings).toFixed(2));
  const marginPct = salePrice > 0 ? +((resellerEarnings / salePrice) * 100).toFixed(1) : 0;
  const overCap = markupNum > maxMarkup;

  const doImport = async () => {
    if (!user) { navigate("/login"); return; }
    if (overCap) {
      toast({ title: "Markup too high", description: `Max allowed is ${maxMarkup}%.`, variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/listings/import", { listing_id: listing.id, markup_pct: markupNum });
      toast({ title: "Imported to your store", description: `You'll pocket ${formatPrice(resellerEarnings)} per sale.` });
      setOpen(false);
      onImported?.(data.id);
    } catch (err) {
      toast({ title: "Import failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const RowLine = DropshipRowLine;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className="h-11" data-testid="dropship-import-btn">
          <PackagePlus className="h-4 w-4 mr-2" /> Import & resell
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="dropship-import-dialog">
        <DialogHeader><DialogTitle>Import to your store</DialogTitle></DialogHeader>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Sell this item without holding inventory. Set your markup — the original seller fulfills, you keep the difference minus the platform fee.
        </p>

        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <Label htmlFor="dropship-markup">Markup %</Label>
            <span className="text-[11px] text-neutral-500 dark:text-neutral-400">Max allowed: {maxMarkup}%</span>
          </div>
          <Input
            id="dropship-markup"
            type="number"
            min="0"
            max={maxMarkup}
            value={markup}
            onChange={(e) => setMarkup(e.target.value)}
            className={`mt-1 ${overCap ? "border-red-500 focus-visible:ring-red-500" : ""}`}
            data-testid="dropship-markup-input"
          />
          {/* Quick markup presets */}
          <div className="mt-2 flex gap-1.5">
            {[10, 20, 35, 50].filter((v) => v <= maxMarkup).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setMarkup(v)}
                className={`px-2.5 h-7 rounded-full text-xs font-medium transition ${Number(markup) === v ? "bg-[#DC2626] text-white" : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-neutral-700"}`}
                data-testid={`dropship-markup-preset-${v}`}
              >
                {v}%
              </button>
            ))}
          </div>
        </div>

        {/* Earnings preview */}
        <div className="mt-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-gradient-to-br from-neutral-50 to-white dark:from-neutral-900 dark:to-neutral-950 p-4 space-y-1.5" data-testid="dropship-earnings-preview">
          <RowLine label="Original seller price" value={formatPrice(basePrice)} />
          <RowLine label={`Your markup (+${markupNum}%)`} value={`+${formatPrice(salePrice - basePrice)}`} tone="text-[#1E40AF]" />
          <div className="h-px bg-neutral-200 dark:bg-neutral-800 my-1.5" />
          <RowLine label="Buyer pays (your listing)" value={formatPrice(salePrice)} tone="font-semibold text-neutral-900 dark:text-neutral-100" />
          <RowLine label={`Platform fee (${platformFeePct}%)`} value={`−${formatPrice(platformFee)}`} tone="text-neutral-500" />
          <RowLine label="Paid to original seller" value={`−${formatPrice(sourceEarnings)}`} tone="text-neutral-500" />
          <div className="h-px bg-neutral-200 dark:bg-neutral-800 my-1.5" />
          <div className="flex justify-between items-baseline">
            <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">You earn per sale</span>
            <div className="text-right">
              <div className="text-xl font-extrabold text-emerald-600 tabular-nums" data-testid="dropship-earn-amount">
                {formatPrice(resellerEarnings)}
              </div>
              <div className="text-[11px] text-neutral-500 dark:text-neutral-400 tabular-nums" data-testid="dropship-margin-pct">
                {marginPct}% margin
              </div>
            </div>
          </div>
          {resellerEarnings <= 0 && (
            <div className="mt-1 text-[11px] text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-lg px-2 py-1">
              Your markup won&apos;t cover the platform fee. Bump it up a bit.
            </div>
          )}
          {overCap && (
            <div className="mt-1 text-[11px] text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-lg px-2 py-1">
              Markup exceeds the platform cap of {maxMarkup}%.
            </div>
          )}
          <div className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
            Note: earnings stay <span className="font-medium">frozen</span> until the buyer confirms delivery.
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="button" className="bg-[#DC2626] hover:bg-[#e01d1b]" onClick={doImport} disabled={loading || overCap || resellerEarnings <= 0} data-testid="dropship-import-submit">
            {loading ? "Importing…" : `Import & earn ${formatPrice(resellerEarnings)}/sale`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ListingDetail = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useLang();
  const { toast } = useToast();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeImg, setActiveImg] = useState(0);
  const [fav, setFav] = useState(false);
  const [inCart, setInCart] = useState(false);
  const [bundle, setBundle] = useState([]);
  const [myStoreSlug, setMyStoreSlug] = useState(null);

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
      api.get("/my/store").then((r) => setMyStoreSlug(r.data?.slug || null)).catch(() => {});
    }
    // Capture Storefront Push referral so it survives the buyer's checkout journey.
    const ref = searchParams.get("ref");
    if (ref === "push") {
      try { sessionStorage.setItem("share_ref", "push"); } catch (e) { /* ignored */ }
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
        <ChevronLeft className="h-4 w-4" /> {t("listing.back")}
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
                  className={`aspect-square rounded-xl overflow-hidden ring-2 transition ${activeImg === i ? "ring-[#DC2626] ring-offset-2 ring-offset-white dark:ring-offset-neutral-950" : "ring-transparent hover:ring-neutral-200 dark:hover:ring-neutral-700"}`}
                >
                  <img src={img} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Info column */}
        <div>
          <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#1E40AF] bg-[#1E40AF]/10 border border-[#1E40AF]/20 rounded-full px-3 py-1">
            {listing.category_name}
          </span>
          <div className="mt-2 flex items-start justify-between gap-4">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">{listing.title}</h1>
            <button
              onClick={() => { navigator.clipboard.writeText(window.location.href); toast({ title: t("listing.linkCopied") }); }}
              className="h-10 w-10 rounded-full grid place-items-center border border-neutral-200 dark:border-neutral-800 text-neutral-500 dark:text-neutral-300 hover:text-[#DC2626] hover:border-[#1E40AF] transition shrink-0"
              aria-label={t("listing.share")}
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
              <span className="text-neutral-700 dark:text-neutral-300">{listing.shipping_paid_by === "seller" ? t("listing.freeShipping") : t("listing.buyerPays")}</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-3 py-2">
              <div className="h-7 w-7 rounded-lg bg-emerald-50 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 grid place-items-center"><Shield className="h-3.5 w-3.5" /></div>
              <span className="text-neutral-700 dark:text-neutral-300">{t("listing.buyerProtection")}</span>
            </div>
          </div>

          {!isOwn && !isSold && (
            <div className="mt-6 space-y-2.5">
              <Button
                onClick={buyNow}
                className="w-full h-12 bg-gradient-to-r from-[#1E40AF] to-[#3B82F6] hover:brightness-105 text-white text-base font-bold rounded-full shadow-lg shadow-[#DC2626]/25"
                data-testid="buy-now-btn"
              >
                {t("listing.buyNow")} · {formatPrice(listing.price)}
              </Button>
              <div className="grid grid-cols-2 gap-2">
                <Button onClick={addToCart} variant="outline" className="h-11 rounded-full" disabled={inCart} data-testid="add-to-cart-btn">
                  <ShoppingCart className="h-4 w-4 mr-2" /> {inCart ? t("listing.inCart") : t("listing.addToCart")}
                </Button>
                <Button onClick={toggleFav} variant="outline" className="h-11 rounded-full" data-testid="fav-toggle-btn">
                  <Heart className={`h-4 w-4 mr-2 ${fav ? "fill-[#DC2626] text-[#DC2626]" : ""}`} />
                  {fav ? t("listing.saved") : t("listing.save")}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <AffiliateShareButton listingId={listing.id} />
                <DropshipImportButton listing={listing} onImported={(id) => navigate(`/listing/${id}`)} />
              </div>
              <Button variant="ghost" className="w-full h-11 rounded-full" onClick={() => { if (!user) { navigate("/login"); return; } navigate(`/chat/${listing.id}/${listing.seller_id}`); }}>
                <MessageCircle className="h-4 w-4 mr-2" /> {t("listing.messageSeller")}
              </Button>
            </div>
          )}
          {isOwn && (
            <div className="mt-6 p-4 rounded-2xl bg-orange-50 dark:bg-[#1E40AF]/10 border border-orange-200 dark:border-orange-500/30 space-y-3">
              <div className="text-sm text-neutral-700 dark:text-neutral-200">
                {t("listing.yourListing")} <Link to="/profile?tab=listings" className="text-[#DC2626] font-semibold hover:underline">{t("listing.profile")}</Link>.
              </div>
              <StorefrontShareButton listing={listing} storeSlug={myStoreSlug} label="Share to boost sales" className="w-full" />
            </div>
          )}
          {isSold && !isOwn && (
            <div className="mt-6 p-4 rounded-2xl bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-sm text-neutral-600 dark:text-neutral-300">
              {t("listing.itemSold")}
            </div>
          )}

          <div className="mt-8 border-t border-neutral-200 dark:border-neutral-800 pt-6">
            <h2 className="font-bold text-neutral-900 dark:text-neutral-100 mb-2">{t("listing.description")}</h2>
            <p className="text-neutral-700 dark:text-neutral-300 whitespace-pre-line leading-relaxed">{listing.description}</p>
          </div>

          <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <SellerBlock sellerId={listing.seller_id} sellerName={listing.seller_name} sellerCountry={listing.seller_country} views={listing.views_count} />
          </div>

          <ListingReviews listingId={listing.id} />
        </div>
      </div>

      {/* You may also like */}
      <SimilarItems listingId={listing.id} />

      {/* Smart Bundles */}
      {bundle.length > 0 && (
        <div className="mt-16 sm:mt-20" data-testid="bundles-section">
          <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#1E40AF] bg-[#1E40AF]/10 border border-[#1E40AF]/20 rounded-full px-3 py-1">
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
