import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Search, Store as StoreIcon, Users, ShoppingBag, Sparkles, Heart } from "lucide-react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/context/AuthContext";
import { flagEmoji, countryName } from "@/constants/countries";

const TIER_STYLES = {
  gold: "from-amber-400 to-amber-600 text-white",
  silver: "from-slate-300 to-slate-500 text-white",
  bronze: "from-orange-400 to-orange-600 text-white",
};

const StoreCard = ({ store, categoryMap = {}, currentCategoryId }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [following, setFollowing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [followers, setFollowers] = useState(store.followers_count || 0);

  const trackDiscovery = () => {
    if (!currentCategoryId) return;
    // Fire-and-forget — never blocks navigation.
    api.post(`/stores/${store.slug}/discovery`, {
      source: "category",
      category_id: currentCategoryId,
    }).catch(() => {});
  };

  useEffect(() => {
    if (!user) return;
    api.get(`/stores/${store.slug}/follow-status`).then((r) => setFollowing(!!r.data?.following)).catch(() => {});
  }, [user, store.slug]);

  const toggle = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!user) { toast({ title: "Sign in to follow stores", variant: "destructive" }); return; }
    setLoading(true);
    try {
      const { data } = await api.post(`/stores/${store.slug}/follow`);
      const isFollowing = !!data?.following;
      setFollowing(isFollowing);
      setFollowers((prev) => prev + (isFollowing ? 1 : -1));
    } catch (err) {
      toast({ title: err.response?.data?.detail || "Could not follow store", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Link
      to={`/store/${store.slug}`}
      onClick={trackDiscovery}
      className="group block rounded-2xl overflow-hidden bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all"
      data-testid={`store-card-${store.slug}`}
    >
      <div className="relative h-28 bg-gradient-to-br from-[#5459E8] via-[#FF5722] to-[#DC2626]">
        {store.banner && (
          <img src={store.banner} alt="" className="w-full h-full object-cover" />
        )}
        {store.verified_tier && store.verified_tier !== "none" && TIER_STYLES[store.verified_tier] && (
          <span className={`absolute top-2 right-2 text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full bg-gradient-to-r ${TIER_STYLES[store.verified_tier]} font-semibold shadow`}>
            {store.verified_tier}
          </span>
        )}
      </div>
      <div className="px-4 pt-8 pb-4 relative">
        <div className="absolute -top-8 left-4 h-14 w-14 rounded-xl bg-white dark:bg-neutral-900 ring-2 ring-white dark:ring-neutral-900 shadow-md overflow-hidden grid place-items-center text-lg font-bold text-neutral-700 dark:text-neutral-100">
          {store.logo ? (
            <img src={store.logo} alt="" className="w-full h-full object-cover" />
          ) : (
            store.name?.[0]?.toUpperCase() || "S"
          )}
        </div>
        <div className="font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-1 group-hover:text-[#2563EB] transition">{store.name}</div>
        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
          {store.owner_username && (
            <span className="text-[11px] text-neutral-400 dark:text-neutral-500">by @{store.owner_username}</span>
          )}
          {store.country && flagEmoji(store.country) && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 dark:text-neutral-300"
              title={`Based in ${countryName(store.country)}`}
              data-testid={`store-country-${store.slug}`}
            >
              <span aria-hidden="true">{flagEmoji(store.country)}</span>
              {countryName(store.country)}
            </span>
          )}
        </div>
        {store.tagline && (
          <div className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">{store.tagline}</div>
        )}
        {store.category_ids?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1" data-testid={`store-cats-${store.slug}`}>
            {store.category_ids.slice(0, 3).map((cid) => {
              const cat = categoryMap[cid];
              if (!cat) return null;
              return (
                <span key={cid} className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#EFF6FF] text-[#2563EB] dark:bg-[#4045C7]/30 dark:text-[#93C5FD]">
                  {cat.name}
                </span>
              );
            })}
          </div>
        )}
        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs text-neutral-600 dark:text-neutral-400">
            <span className="flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {followers}</span>
            <span className="flex items-center gap-1"><ShoppingBag className="h-3.5 w-3.5" /> {store.total_sales || 0}</span>
          </div>
          <button
            onClick={toggle}
            disabled={loading}
            className={`h-8 px-3 rounded-full text-xs font-semibold transition flex items-center gap-1 shrink-0 disabled:opacity-60 ${
              following
                ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-950 dark:text-emerald-300"
                : "bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white hover:brightness-110"
            }`}
            data-testid={`store-follow-btn-${store.slug}`}
            aria-pressed={following}
          >
            <Heart className={`h-3.5 w-3.5 ${following ? "fill-current" : ""}`} />
            {following ? "Following" : "Follow"}
          </button>
        </div>
      </div>
    </Link>
  );
};

const StoresMarketplace = () => {
  const [q, setQ] = useState("");
  const [tier, setTier] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 48 };
      if (q.trim()) params.q = q.trim();
      if (tier) params.tier = tier;
      if (categoryId) params.category = categoryId;
      const { data } = await api.get("/stores-search", { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {
      setItems([]); setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [q, tier, categoryId]);

  useEffect(() => {
    const h = setTimeout(load, 250); // debounce
    return () => clearTimeout(h);
  }, [load]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-10">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#5459E8] via-[#FF5722] to-[#DC2626] px-6 sm:px-10 py-10 shadow-lg">
        <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-white/20 blur-3xl" />
        <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-[#2563EB]/25 blur-3xl" />
        <div className="relative">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 backdrop-blur text-white text-xs font-semibold tracking-widest uppercase">
            <Sparkles className="h-3.5 w-3.5" /> Stores marketplace
          </div>
          <h1 className="mt-3 text-3xl sm:text-4xl font-extrabold text-white tracking-tight">Discover verified storefronts</h1>
          <p className="mt-1 text-white/85 text-sm max-w-2xl">Browse trusted sellers by name, follow your favourites, and shop everything they've curated in one place.</p>
        </div>
      </div>

      {/* Search + filter */}
      <div className="mt-6 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
        <div className="relative flex-1">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search stores by name, handle, or tagline…"
            className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
            data-testid="stores-search-input"
          />
        </div>
        <div className="flex gap-2">
          {["", "gold", "silver", "bronze"].map((t) => (
            <Button
              key={t || "all"}
              variant={tier === t ? "default" : "outline"}
              size="sm"
              className={`h-11 px-4 rounded-full ${tier === t ? "bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white border-transparent hover:brightness-110" : ""}`}
              onClick={() => setTier(t)}
              data-testid={`stores-tier-${t || "all"}`}
            >
              {t ? t[0].toUpperCase() + t.slice(1) : "All tiers"}
            </Button>
          ))}
        </div>
      </div>

      {/* Category filter chips */}
      {categories.length > 0 && (
        <div className="mt-4 -mx-4 px-4 overflow-x-auto scrollbar-hide">
          <div className="flex gap-2 min-w-max">
            <button
              onClick={() => setCategoryId("")}
              data-testid="stores-cat-all"
              className={`whitespace-nowrap h-9 px-4 rounded-full text-xs font-semibold transition border ${
                !categoryId
                  ? "bg-neutral-900 text-white border-transparent dark:bg-white dark:text-neutral-900"
                  : "bg-white text-neutral-700 border-neutral-200 hover:border-[#2563EB] hover:text-[#2563EB] dark:bg-neutral-900 dark:text-neutral-200 dark:border-neutral-700"
              }`}
            >
              All categories
            </button>
            {categories.map((c) => (
              <button
                key={c.id}
                onClick={() => setCategoryId(c.id === categoryId ? "" : c.id)}
                data-testid={`stores-cat-${c.slug}`}
                className={`whitespace-nowrap h-9 px-4 rounded-full text-xs font-semibold transition border ${
                  categoryId === c.id
                    ? "bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white border-transparent shadow-sm"
                    : "bg-white text-neutral-700 border-neutral-200 hover:border-[#2563EB] hover:text-[#2563EB] dark:bg-neutral-900 dark:text-neutral-200 dark:border-neutral-700"
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Result count */}
      <div className="mt-4 text-sm text-neutral-500 dark:text-neutral-400">
        {loading ? "Loading stores…" : (
          <>
            <span className="tabular-nums font-semibold text-neutral-800 dark:text-neutral-100">{total}</span>
            {" "}{total === 1 ? "store" : "stores"} found{q ? ` for "${q}"` : ""}
          </>
        )}
      </div>

      {/* Grid */}
      {!loading && items.length === 0 ? (
        <div className="mt-10 rounded-2xl border-2 border-dashed border-neutral-200 dark:border-neutral-800 p-10 text-center">
          <StoreIcon className="h-8 w-8 mx-auto text-neutral-400" />
          <div className="mt-3 font-semibold dark:text-neutral-100">No stores matched</div>
          <div className="text-sm text-neutral-500 dark:text-neutral-400">Try a different name or clear the tier filter.</div>
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {items.map((s) => <StoreCard key={s.id} store={s} currentCategoryId={categoryId} categoryMap={Object.fromEntries(categories.map((c) => [c.id, c]))} />)}
        </div>
      )}
    </div>
  );
};

export default StoresMarketplace;
