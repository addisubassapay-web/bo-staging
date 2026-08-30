import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { useLang } from "@/context/LanguageContext";
import { Sparkles, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * SimilarItems — "You may also like" horizontal strip on ListingDetail.
 * Powered by GET /api/listings/{id}/similar (same category + ±40% price band + popularity).
 */
const SimilarItems = ({ listingId }) => {
  const { t } = useLang();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const scrollRef = React.useRef(null);

  useEffect(() => {
    setLoading(true);
    api
      .get(`/listings/${listingId}/similar`, { params: { limit: 12 } })
      .then((r) => setItems(r.data || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [listingId]);

  const scrollBy = (dir) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.85, behavior: "smooth" });
  };

  if (!loading && items.length === 0) return null;

  return (
    <div className="mt-16 sm:mt-20" data-testid="similar-items-section">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] font-semibold text-[#1E40AF] bg-[#1E40AF]/10 border border-[#1E40AF]/20 rounded-full px-3 py-1">
            <Sparkles className="h-3 w-3" /> {t("similar.kicker")}
          </span>
          <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
            {t("similar.title")}
          </h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {t("similar.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => scrollBy(-1)}
            aria-label="Scroll left"
            className="h-10 w-10 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#1E40AF] grid place-items-center transition text-neutral-700 dark:text-neutral-200"
            data-testid="similar-scroll-left"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => scrollBy(1)}
            aria-label="Scroll right"
            className="h-10 w-10 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#1E40AF] grid place-items-center transition text-neutral-700 dark:text-neutral-200"
            data-testid="similar-scroll-right"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="aspect-square bg-neutral-100 dark:bg-neutral-800 animate-pulse rounded-2xl" />
          ))}
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="mt-5 flex gap-3 sm:gap-4 overflow-x-auto scrollbar-hide snap-x snap-mandatory pb-2"
          data-testid="similar-items-scroll"
        >
          {items.map((l) => (
            <div key={l.id} className="w-[48%] sm:w-[32%] lg:w-[18%] shrink-0 snap-start" data-testid={`similar-item-${l.id}`}>
              <ProductCard listing={l} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SimilarItems;
