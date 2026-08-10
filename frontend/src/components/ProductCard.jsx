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
    <Link to={`/listing/${listing.id}`} className="group block">
      <div className="relative aspect-square rounded-lg overflow-hidden bg-neutral-100">
        <img
          src={listing.images?.[0] || "https://picsum.photos/seed/placeholder/400"}
          alt={listing.title}
          loading="lazy"
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
        />
        {sold && (
          <div className="absolute inset-0 bg-black/50 grid place-items-center">
            <span className="bg-white text-neutral-900 font-semibold px-3 py-1 rounded text-sm">SOLD</span>
          </div>
        )}
        {priceDropRecent && !sold && (
          <span
            className="absolute top-2 left-2 inline-flex items-center gap-1 bg-emerald-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow ring-2 ring-emerald-300/60 animate-pulse"
            data-testid="price-drop-badge"
          >
            <TrendingDown className="h-3 w-3" /> -{priceDropRecent.pct}%
          </span>
        )}
        <button
          onClick={toggleFav}
          className="absolute top-2 right-2 h-8 w-8 rounded-full bg-white/90 hover:bg-white grid place-items-center shadow-sm transition"
          aria-label="Favorite"
        >
          <Heart className={`h-4 w-4 ${fav ? "fill-[#FF211F] text-[#FF211F]" : "text-neutral-700"}`} />
        </button>
      </div>
      <div className="mt-2 px-0.5">
        <div className="flex items-center gap-1.5 text-sm text-neutral-800 line-clamp-2 leading-snug min-h-[2.5rem]">
          {sellerVerified && (
            <span
              title="Verified seller"
              className="inline-flex items-center justify-center h-4 w-4 shrink-0 rounded-full bg-gradient-to-br from-yellow-300 to-amber-500 text-white shadow-sm ring-1 ring-amber-500/60"
              data-testid="verified-seller-badge"
            >
              <ShieldCheck className="h-2.5 w-2.5" />
            </span>
          )}
          <span>{listing.title}</span>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="font-semibold text-neutral-900">
            {formatPrice(listing.price)}
            {priceDropRecent && <span className="ml-1 text-xs text-neutral-400 line-through">${priceDropRecent.prev.toFixed(2)}</span>}
          </span>
          {listing.likes_count > 0 && (
            <span className="text-xs text-neutral-500 flex items-center gap-1">
              <Heart className="h-3 w-3" /> {listing.likes_count}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
};

export default ProductCard;
