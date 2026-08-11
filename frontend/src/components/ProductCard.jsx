import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heart, ShieldCheck, TrendingDown } from "lucide-react";
import { formatPrice } from "@/lib/api";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const ProductCard = ({ listing, isFavorite = false, onFavoriteChange }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [fav, setFav] = useState(isFavorite);
  const [busy, setBusy] = useState(false);
  const [sellerVerified, setSellerVerified] = useState(false);

  useEffect(() => {
    // Cheap client cache to avoid re-fetching seller info repeatedly
    if (!listing?.seller_id) return;
    const key = `mercari_seller_${listing.seller_id}`;
    const cached = sessionStorage.getItem(key);
    if (cached !== null) {
      setSellerVerified(cached === "1");
      return;
    }
    api.get(`/users/${listing.seller_id}/public`).then((r) => {
      const v = r.data?.seller_status === "approved";
      setSellerVerified(v);
      sessionStorage.setItem(key, v ? "1" : "0");
    }).catch(() => {});
  }, [listing?.seller_id]);

  const toggleFav = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!user) {
      toast({ title: "Log in to save items", description: "Create an account or log in first." });
      return;
    }
    if (busy) return;
    setBusy(true);
    try {
      if (fav) {
        await api.delete(`/favorites/${listing.id}`);
        setFav(false);
        onFavoriteChange && onFavoriteChange(listing.id, false);
      } else {
        await api.post(`/favorites/${listing.id}`);
        setFav(true);
        onFavoriteChange && onFavoriteChange(listing.id, true);
      }
    } catch {
      toast({ title: "Something went wrong", variant: "destructive" });
    } finally {
      setBusy(false);
    }
  };

  const sold = listing.status === "sold";
  const priceDropRecent = (() => {
    if (!listing.price_drop_at) return null;
    const ago = Date.now() - new Date(listing.price_drop_at).getTime();
    if (ago > 7 * 24 * 3600 * 1000) return null;
    const prev = Number(listing.previous_price || 0);
    const cur = Number(listing.price || 0);
    if (!prev || prev <= cur) return null;
    return { pct: Math.round(((prev - cur) / prev) * 100), prev };
  })();

  return (
    <Link
      to={`/listing/${listing.id}`}
      className="group block rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-[#FF7A18]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-neutral-950"
      data-testid={`product-card-${listing.id}`}
    >
      <div className="relative aspect-square rounded-2xl overflow-hidden bg-neutral-100 dark:bg-neutral-800 ring-1 ring-black/[0.04] dark:ring-white/10 shadow-[0_1px_2px_rgba(0,0,0,0.04)] group-hover:shadow-[0_10px_30px_-12px_rgba(255,33,31,0.28)] group-hover:-translate-y-0.5 transition-all duration-300 ease-out">
        <img
          src={listing.images?.[0] || "https://picsum.photos/seed/placeholder/400"}
          alt={listing.title}
          loading="lazy"
          className="w-full h-full object-cover group-hover:scale-[1.06] transition-transform duration-500 ease-out"
        />
        {/* Soft bottom fade for legibility of any overlaid badges */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/25 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

        {sold && (
          <div className="absolute inset-0 bg-gradient-to-br from-black/70 via-black/45 to-black/30 grid place-items-center backdrop-blur-[1px]">
            <span className="bg-white text-neutral-900 font-bold tracking-wide px-3.5 py-1 rounded-full text-xs shadow-lg uppercase">
              Sold
            </span>
          </div>
        )}
        {priceDropRecent && !sold && (
          <span
            className="absolute top-2.5 left-2.5 inline-flex items-center gap-1 bg-emerald-600 text-white text-[10px] font-bold px-2 py-1 rounded-full shadow ring-2 ring-emerald-300/60"
            data-testid="price-drop-badge"
          >
            <TrendingDown className="h-3 w-3" /> -{priceDropRecent.pct}%
          </span>
        )}
        <button
          onClick={toggleFav}
          aria-label={fav ? "Remove from favorites" : "Add to favorites"}
          className={`absolute top-2.5 right-2.5 h-9 w-9 rounded-full grid place-items-center shadow-sm ring-1 backdrop-blur-md transition-all duration-200 ${
            fav
              ? "bg-white text-[#FF211F] ring-[#FF211F]/30 scale-100"
              : "bg-white/85 dark:bg-neutral-900/70 text-neutral-700 dark:text-neutral-200 ring-black/5 dark:ring-white/10 opacity-0 group-hover:opacity-100 scale-90 group-hover:scale-100"
          }`}
          data-testid={`favorite-btn-${listing.id}`}
        >
          <Heart className={`h-4 w-4 ${fav ? "fill-[#FF211F] text-[#FF211F]" : ""}`} />
        </button>
      </div>
      <div className="mt-3 px-0.5">
        <div className="flex items-start gap-1.5 text-sm text-neutral-800 dark:text-neutral-100 line-clamp-2 leading-snug min-h-[2.5rem] font-medium">
          {sellerVerified && (
            <span
              title="Verified seller"
              className="inline-flex items-center justify-center h-4 w-4 shrink-0 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 text-white shadow-sm ring-1 ring-amber-500/50 mt-0.5"
              data-testid="verified-seller-badge"
            >
              <ShieldCheck className="h-2.5 w-2.5" />
            </span>
          )}
          <span className="group-hover:text-[#FF211F] transition-colors">{listing.title}</span>
        </div>
        <div className="mt-1.5 flex items-baseline justify-between gap-2">
          <div className="flex items-baseline gap-1.5 min-w-0">
            <span className="font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">
              {formatPrice(listing.price)}
            </span>
            {priceDropRecent && (
              <span className="text-xs text-neutral-400 dark:text-neutral-500 line-through tabular-nums">
                ${priceDropRecent.prev.toFixed(2)}
              </span>
            )}
          </div>
          {listing.likes_count > 0 && (
            <span className="text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-1 tabular-nums shrink-0">
              <Heart className="h-3 w-3" /> {listing.likes_count}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
};

export default ProductCard;
