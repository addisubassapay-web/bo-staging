import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Heart } from "lucide-react";
import { formatPrice } from "@/lib/api";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const ProductCard = ({ listing, isFavorite = false, onFavoriteChange }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [fav, setFav] = useState(isFavorite);
  const [busy, setBusy] = useState(false);

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
        <button
          onClick={toggleFav}
          className="absolute top-2 right-2 h-8 w-8 rounded-full bg-white/90 hover:bg-white grid place-items-center shadow-sm transition"
          aria-label="Favorite"
        >
          <Heart className={`h-4 w-4 ${fav ? "fill-[#FF211F] text-[#FF211F]" : "text-neutral-700"}`} />
        </button>
      </div>
      <div className="mt-2 px-0.5">
        <div className="text-sm text-neutral-800 line-clamp-2 leading-snug min-h-[2.5rem]">
          {listing.title}
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="font-semibold text-neutral-900">{formatPrice(listing.price)}</span>
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
