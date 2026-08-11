import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Store as StoreIcon, Award, ShieldCheck, Users, Package, Calendar, Star } from "lucide-react";
import { VerificationBadges } from "@/components/VerificationBadges";

const tierMeta = {
  none: null,
  bronze: { cls: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30", label: "Bronze verified" },
  silver: { cls: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/20 dark:text-slate-200 dark:border-slate-500/30", label: "Silver verified" },
  gold:   { cls: "bg-yellow-100 text-yellow-900 border-yellow-200 dark:bg-yellow-500/20 dark:text-yellow-200 dark:border-yellow-500/30", label: "Gold verified" },
};

const SORTS = [
  { value: "newest",     label: "Newest first" },
  { value: "price_asc",  label: "Price: low to high" },
  { value: "price_desc", label: "Price: high to low" },
  { value: "popular",    label: "Most popular" },
];

const StorePage = () => {
  const { slug } = useParams();
  const [store, setStore] = useState(null);
  const [listings, setListings] = useState([]);
  const [owner, setOwner] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState("newest");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/stores/${slug}`).then((r) => setStore(r.data)),
      api.get(`/stores/${slug}/listings`).then((r) => setListings(r.data)),
    ]).catch(() => {}).finally(() => setLoading(false));
  }, [slug]);

  useEffect(() => {
    if (store?.owner_id) {
      api.get(`/users/${store.owner_id}/public`).then((r) => setOwner(r.data)).catch(() => {});
    }
  }, [store]);

  const sortedListings = useMemo(() => {
    const copy = [...listings];
    switch (sort) {
      case "price_asc":  return copy.sort((a, b) => a.price - b.price);
      case "price_desc": return copy.sort((a, b) => b.price - a.price);
      case "popular":    return copy.sort((a, b) => (b.likes_count || 0) - (a.likes_count || 0));
      default:           return copy.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }
  }, [listings, sort]);

  if (loading) return <div className="max-w-6xl mx-auto px-4 py-8 text-neutral-500">Loading…</div>;
  if (!store) return <div className="max-w-6xl mx-auto px-4 py-16 text-center text-neutral-600 dark:text-neutral-300">Store not found.</div>;

  const tier = tierMeta[store.verified_tier];

  return (
    <div className="bg-white dark:bg-neutral-950" data-testid="store-page">
      {/* Hero — gradient with optional banner overlay */}
      <div className="relative h-40 md:h-64 overflow-hidden bg-gradient-to-br from-[#FF7A18] via-[#FF5722] to-[#FF211F]">
        {store.banner && (
          <img src={store.banner} alt="" className="absolute inset-0 h-full w-full object-cover opacity-70" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-black/10 to-transparent" />
        <div className="pointer-events-none absolute -top-10 -right-10 h-56 w-56 rounded-full bg-white/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 left-1/3 h-56 w-56 rounded-full bg-black/25 blur-3xl" />
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="-mt-12 md:-mt-16 flex items-end gap-4 flex-wrap">
          <div className="h-20 w-20 md:h-28 md:w-28 rounded-2xl bg-white dark:bg-neutral-900 ring-4 ring-white dark:ring-neutral-900 shadow-lg grid place-items-center overflow-hidden shrink-0">
            {store.logo ? (
              <img src={store.logo} alt="" className="w-full h-full object-cover" />
            ) : (
              <StoreIcon className="h-10 w-10 text-[#FF211F]" />
            )}
          </div>
          <div className="pb-2 flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl md:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100" data-testid="store-name">
                {store.name}
              </h1>
              {tier && (
                <Badge className={`gap-1 border ${tier.cls}`} data-testid="store-tier-badge">
                  <Award className="h-3 w-3" /> {tier.label}
                </Badge>
              )}
              {owner && <VerificationBadges user={owner} showLabels={false} />}
            </div>
            {store.tagline && <p className="text-neutral-600 dark:text-neutral-300 text-sm mt-1">{store.tagline}</p>}
          </div>
        </div>

        {/* Stat pills */}
        <div className="mt-6 grid grid-cols-3 gap-3 sm:max-w-lg">
          <StatPill icon={Package} label="Sales" value={store.total_sales?.toLocaleString?.() ?? "0"} tone="orange" />
          <StatPill icon={Users}   label="Followers" value={store.followers_count?.toLocaleString?.() ?? "0"} tone="sky" />
          <StatPill icon={Calendar} label="Since" value={new Date(store.created_at).toLocaleDateString(undefined, { month: "short", year: "numeric" })} tone="emerald" />
        </div>

        {store.bio && (
          <p className="mt-6 text-neutral-700 dark:text-neutral-300 leading-relaxed max-w-3xl">
            {store.bio}
          </p>
        )}

        <div className="mt-6 inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 text-emerald-800 dark:text-emerald-200 text-sm px-3 py-1.5">
          <ShieldCheck className="h-4 w-4" />
          Purchases here are protected by Mercari Buyer Protection.
        </div>

        {/* Listings block */}
        <div className="mt-10 pb-14">
          <div className="flex items-end justify-between mb-5 gap-4 flex-wrap">
            <div>
              <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
                Storefront
              </span>
              <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
                <Star className="h-6 w-6 text-[#FF7A18]" /> Store listings
              </h2>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
                {listings.length} {listings.length === 1 ? "item" : "items"} on offer
              </p>
            </div>
            {listings.length > 0 && (
              <Select value={sort} onValueChange={setSort}>
                <SelectTrigger className="w-[180px]" data-testid="store-sort-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SORTS.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>

          {listings.length === 0 ? (
            <div className="text-center py-16 rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-500 dark:text-neutral-400" data-testid="store-empty">
              <Package className="h-10 w-10 mx-auto text-neutral-300 dark:text-neutral-600 mb-2" />
              This store has no active listings yet.
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4" data-testid="store-listings-grid">
              {sortedListings.map((l) => <ProductCard key={l.id} listing={l} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const StatPill = ({ icon: Icon, label, value, tone }) => {
  const tones = {
    orange:  "text-[#FF7A18] bg-[#FF7A18]/10 border-[#FF7A18]/20",
    sky:     "text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-500/15 border-sky-200 dark:border-sky-500/30",
    emerald: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15 border-emerald-200 dark:border-emerald-500/30",
  };
  return (
    <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className={`h-8 w-8 rounded-lg border grid place-items-center ${tones[tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mt-2">{label}</div>
      <div className="font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{value}</div>
    </div>
  );
};

export default StorePage;
