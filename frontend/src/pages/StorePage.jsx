import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Store as StoreIcon, Award, ShieldCheck, Users, Package, Calendar, Star,
  Heart, HeartOff, Share2, TrendingUp, Sparkles, Zap, Flame, PackagePlus,
} from "lucide-react";
import { VerificationBadges } from "@/components/VerificationBadges";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

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
  const { user } = useAuth();
  const { toast } = useToast();
  const [store, setStore] = useState(null);
  const [listings, setListings] = useState([]);
  const [owner, setOwner] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState("newest");
  const [activeCat, setActiveCat] = useState("all");
  const [following, setFollowing] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [scrolled, setScrolled] = useState(false);

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
    if (user && store) {
      api.get(`/stores/${slug}/follow-status`).then((r) => setFollowing(!!r.data.following)).catch(() => {});
    }
  }, [store, user, slug]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 220);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const toggleFollow = async () => {
    if (!user) { toast({ title: "Log in to follow", variant: "destructive" }); return; }
    setFollowBusy(true);
    try {
      const { data } = await api.post(`/stores/${slug}/follow`);
      setFollowing(!!data.following);
      setStore((s) => s ? { ...s, followers_count: data.followers_count } : s);
      toast({ title: data.following ? "Following" : "Unfollowed" });
    } catch (e) {
      toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setFollowBusy(false); }
  };

  const shareStore = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try { await navigator.share({ title: store.name, url }); } catch (e) { /* cancelled */ }
    } else {
      try { await navigator.clipboard.writeText(url); toast({ title: "Store link copied" }); } catch (e) { /* ignore */ }
    }
  };

  // Derived: category chips from listings
  const catChips = useMemo(() => {
    const map = new Map();
    listings.forEach((l) => {
      if (l.category_name) {
        const k = l.category_id || l.category_name;
        if (!map.has(k)) map.set(k, { id: k, name: l.category_name, count: 0 });
        map.get(k).count += 1;
      }
    });
    return Array.from(map.values()).sort((a, b) => b.count - a.count);
  }, [listings]);

  const filteredAndSorted = useMemo(() => {
    const now = Date.now();
    const filtered = activeCat === "all" ? listings : listings.filter((l) => (l.category_id || l.category_name) === activeCat);
    const copy = [...filtered];
    switch (sort) {
      case "price_asc":  return copy.sort((a, b) => a.price - b.price);
      case "price_desc": return copy.sort((a, b) => b.price - a.price);
      case "popular":    return copy.sort((a, b) => (b.likes_count || 0) - (a.likes_count || 0));
      default:           return copy.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }
  }, [listings, sort, activeCat]);

  const newArrivals = useMemo(() => {
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return [...listings]
      .filter((l) => new Date(l.created_at).getTime() >= cutoff)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 8);
  }, [listings]);

  const hotPicks = useMemo(() => {
    return [...listings]
      .sort((a, b) => (b.likes_count || 0) - (a.likes_count || 0))
      .slice(0, 8)
      .filter((l) => (l.likes_count || 0) > 0);
  }, [listings]);

  if (loading) return <div className="max-w-6xl mx-auto px-4 py-8 text-neutral-500">Loading…</div>;
  if (!store) return <div className="max-w-6xl mx-auto px-4 py-16 text-center text-neutral-600 dark:text-neutral-300">Store not found.</div>;

  const tier = tierMeta[store.verified_tier];
  const totalItems = listings.length;
  const isOwn = user && store.owner_id === user.id;

  return (
    <div className="bg-neutral-50 dark:bg-neutral-950 min-h-screen" data-testid="store-page">
      {/* Sticky mini-header when scrolled */}
      {scrolled && (
        <div className="fixed top-0 left-0 right-0 z-40 bg-white/95 dark:bg-neutral-900/95 backdrop-blur border-b border-neutral-200 dark:border-neutral-800 shadow-sm animate-in slide-in-from-top-2" data-testid="store-sticky-nav">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-neutral-100 dark:bg-neutral-800 overflow-hidden shrink-0">
              {store.logo ? <img src={store.logo} alt="" className="w-full h-full object-cover" /> : <StoreIcon className="h-full w-full p-2 text-[#FF211F]" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-bold truncate text-neutral-900 dark:text-neutral-100">{store.name}</div>
              <div className="text-[11px] text-neutral-500">{totalItems} items · {store.followers_count?.toLocaleString?.() ?? 0} followers</div>
            </div>
            {!isOwn && (
              <Button
                size="sm"
                onClick={toggleFollow}
                disabled={followBusy}
                className={`min-h-[36px] rounded-full ${following ? "bg-white text-[#FF211F] border border-[#FF211F] hover:bg-[#FFF3F2]" : "bg-[#FF211F] hover:bg-[#e01d1b] text-white"}`}
                data-testid="store-sticky-follow"
              >
                {following ? "Following" : "Follow"}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Hero — vibrant animated gradient */}
      <div className="relative h-48 sm:h-64 md:h-80 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#FF7A18] via-[#FF3D66] to-[#7C3AED] animate-[gradient_10s_ease_infinite]" style={{ backgroundSize: "200% 200%" }} />
        {store.banner && (
          <img src={store.banner} alt="" className="absolute inset-0 h-full w-full object-cover opacity-60 mix-blend-multiply" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-neutral-50 dark:from-neutral-950 via-black/10 to-transparent" />
        <div className="pointer-events-none absolute -top-10 -right-10 h-64 w-64 rounded-full bg-white/25 blur-3xl animate-pulse" />
        <div className="pointer-events-none absolute -bottom-16 left-1/3 h-56 w-56 rounded-full bg-purple-500/40 blur-3xl" />
        <div className="pointer-events-none absolute top-1/3 left-1/4 h-40 w-40 rounded-full bg-amber-300/40 blur-3xl" />
        <style>{`@keyframes gradient {0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}`}</style>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 relative pb-16">
        {/* Profile card overlapping the hero */}
        <div className="-mt-16 sm:-mt-20 rounded-3xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-xl p-5 sm:p-6" data-testid="store-profile-card">
          <div className="flex items-start gap-4 flex-wrap">
            <div className="h-20 w-20 sm:h-24 sm:w-24 rounded-2xl bg-gradient-to-br from-neutral-50 to-neutral-100 dark:from-neutral-800 dark:to-neutral-900 ring-4 ring-white dark:ring-neutral-900 shadow-md grid place-items-center overflow-hidden shrink-0">
              {store.logo ? <img src={store.logo} alt="" className="w-full h-full object-cover" /> : <StoreIcon className="h-10 w-10 text-[#FF211F]" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100" data-testid="store-name">
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
              {store.bio && <p className="text-neutral-700 dark:text-neutral-300 text-sm mt-2 line-clamp-2 max-w-2xl">{store.bio}</p>}
            </div>
            <div className="flex flex-col sm:flex-row gap-2 shrink-0">
              {!isOwn && (
                <Button
                  onClick={toggleFollow}
                  disabled={followBusy}
                  className={`min-h-[44px] rounded-full px-5 gap-1.5 ${following ? "bg-white text-[#FF211F] border border-[#FF211F] hover:bg-[#FFF3F2]" : "bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white"}`}
                  data-testid="store-follow-btn"
                >
                  {following ? <><HeartOff className="h-4 w-4" /> Following</> : <><Heart className="h-4 w-4" /> Follow</>}
                </Button>
              )}
              <Button
                onClick={shareStore}
                variant="outline"
                className="min-h-[44px] rounded-full px-5 gap-1.5"
                data-testid="store-share-btn"
              >
                <Share2 className="h-4 w-4" /> Share
              </Button>
            </div>
          </div>

          {/* Live stat pills */}
          <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatPill icon={Package} label="Items" value={totalItems.toLocaleString()} tone="orange" />
            <StatPill icon={Users}   label="Followers" value={(store.followers_count ?? 0).toLocaleString()} tone="sky" />
            <StatPill icon={TrendingUp} label="Sales" value={(store.total_sales ?? 0).toLocaleString()} tone="emerald" />
            <StatPill icon={Calendar} label="Since" value={new Date(store.created_at).toLocaleDateString(undefined, { month: "short", year: "numeric" })} tone="purple" />
          </div>

          <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 text-emerald-800 dark:text-emerald-200 text-sm px-3 py-1.5">
            <ShieldCheck className="h-4 w-4" />
            Purchases here are protected by Merchari-global Buyer Protection
          </div>
        </div>

        {/* Owner control panel — high-visibility Publish CTA */}
        {isOwn && (
          <div className="mt-6 rounded-3xl border-2 border-[#FF211F]/20 bg-gradient-to-br from-[#FFF3F2] via-white to-purple-50 dark:from-red-950/30 dark:via-neutral-900 dark:to-purple-950/30 p-5 sm:p-6 shadow-md relative overflow-hidden" data-testid="store-control-panel">
            <div className="pointer-events-none absolute -top-16 -right-16 h-64 w-64 rounded-full bg-[#FF7A18]/15 blur-3xl" />
            <div className="relative flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="h-11 w-11 rounded-2xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] grid place-items-center shrink-0 shadow-lg shadow-[#FF211F]/30">
                  <PackagePlus className="h-5 w-5 text-white" />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18]">Owner controls</div>
                  <h3 className="font-bold text-lg text-neutral-900 dark:text-neutral-100">Grow your store</h3>
                  <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">Publish new items to your storefront instantly.</p>
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                <Link to="/dashboard/list-product">
                  <Button
                    className="min-h-[48px] px-6 rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white font-bold gap-2 shadow-lg shadow-[#FF211F]/30 hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 transition-all"
                    data-testid="store-publish-cta"
                  >
                    <PackagePlus className="h-5 w-5" /> Publish / List Products
                  </Button>
                </Link>
                <Link to="/store/analytics">
                  <Button
                    variant="outline"
                    className="min-h-[48px] rounded-full gap-1.5 border-neutral-300 hover:border-[#FF211F] hover:text-[#FF211F]"
                    data-testid="store-open-dashboard"
                  >
                    <TrendingUp className="h-4 w-4" /> Dashboard
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* New Arrivals strip */}
        {newArrivals.length > 0 && (
          <section className="mt-8" data-testid="store-new-arrivals">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 grid place-items-center shadow-sm">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div>
                  <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">New this week</h2>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Fresh drops from the last 7 days</p>
                </div>
              </div>
              <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/30 rounded-full px-2 py-0.5">
                {newArrivals.length}
              </span>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-3 snap-x snap-mandatory -mx-4 px-4 sm:mx-0 sm:px-0" data-testid="store-new-strip">
              {newArrivals.map((l) => (
                <div key={l.id} className="snap-start shrink-0 w-[45%] sm:w-[220px]">
                  <ProductCard listing={l} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Hot picks strip */}
        {hotPicks.length > 0 && (
          <section className="mt-8" data-testid="store-hot-picks">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] grid place-items-center shadow-sm">
                  <Flame className="h-4 w-4 text-white" />
                </div>
                <div>
                  <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">Hot picks</h2>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Most-favorited in this store</p>
                </div>
              </div>
              <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF211F] bg-[#FFF3F2] border border-[#FF211F]/20 rounded-full px-2 py-0.5">
                {hotPicks.length}
              </span>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-3 snap-x snap-mandatory -mx-4 px-4 sm:mx-0 sm:px-0" data-testid="store-hot-strip">
              {hotPicks.map((l) => (
                <div key={l.id} className="snap-start shrink-0 w-[45%] sm:w-[220px]">
                  <ProductCard listing={l} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Category filter chips + sort */}
        <section className="mt-10 pb-14 rounded-3xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 sm:p-6 shadow-sm">
          <div className="flex items-end justify-between mb-4 gap-4 flex-wrap">
            <div>
              <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-white bg-gradient-to-r from-[#FF7A18] to-[#FF211F] rounded-full px-3 py-1 shadow-sm">
                Storefront
              </span>
              <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
                <Zap className="h-6 w-6 text-[#FF7A18] fill-[#FF7A18]/20" /> Store listings
              </h2>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1 tabular-nums">
                <b>{filteredAndSorted.length}</b> of {totalItems} items on offer
              </p>
            </div>
            {listings.length > 0 && (
              <Select value={sort} onValueChange={setSort}>
                <SelectTrigger className="w-[180px] min-h-[44px]" data-testid="store-sort-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SORTS.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>

          {catChips.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-2 -mx-5 px-5 sm:mx-0 sm:px-0 border-b border-neutral-100 dark:border-neutral-800 mb-5" data-testid="store-cat-chips">
              <button
                type="button"
                onClick={() => setActiveCat("all")}
                className={`min-h-[40px] shrink-0 px-4 rounded-full text-sm font-semibold transition-all active:scale-95 ${activeCat === "all"
                  ? "bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white shadow-md shadow-[#FF211F]/25"
                  : "bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:border-[#FF211F] hover:text-[#FF211F] hover:-translate-y-0.5"}`}
                data-testid="store-cat-all"
              >
                All <span className={`ml-1.5 text-[10px] ${activeCat === "all" ? "opacity-90" : "opacity-60"}`}>{totalItems}</span>
              </button>
              {catChips.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setActiveCat(c.id)}
                  className={`min-h-[40px] shrink-0 px-4 rounded-full text-sm font-semibold transition-all active:scale-95 ${activeCat === c.id
                    ? "bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white shadow-md shadow-[#FF211F]/25"
                    : "bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:border-[#FF211F] hover:text-[#FF211F] hover:-translate-y-0.5"}`}
                  data-testid={`store-cat-${c.id}`}
                >
                  {c.name} <span className={`ml-1.5 text-[10px] ${activeCat === c.id ? "opacity-90" : "opacity-60"}`}>{c.count}</span>
                </button>
              ))}
            </div>
          )}

          <div>
            {filteredAndSorted.length === 0 ? (
              <div className="text-center py-16 rounded-2xl border-2 border-dashed border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-950 text-neutral-500 dark:text-neutral-400" data-testid="store-empty">
                <Package className="h-10 w-10 mx-auto text-neutral-300 dark:text-neutral-600 mb-2" />
                {activeCat === "all" ? "This store has no active listings yet." : "No items in this category."}
                {isOwn && (
                  <div className="mt-4">
                    <Link to="/dashboard/list-product">
                      <Button className="min-h-[44px] rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white gap-1.5" data-testid="store-empty-publish">
                        <PackagePlus className="h-4 w-4" /> Publish your first item
                      </Button>
                    </Link>
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4" data-testid="store-listings-grid">
                {filteredAndSorted.map((l) => (
                  <div key={l.id} className="hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200 rounded-xl">
                    <ProductCard listing={l} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

const StatPill = ({ icon: Icon, label, value, tone }) => {
  const tones = {
    orange:  "text-[#FF7A18] bg-[#FF7A18]/10 border-[#FF7A18]/20",
    sky:     "text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-500/15 border-sky-200 dark:border-sky-500/30",
    emerald: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15 border-emerald-200 dark:border-emerald-500/30",
    purple:  "text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-500/15 border-purple-200 dark:border-purple-500/30",
  };
  return (
    <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className={`h-8 w-8 rounded-lg border grid place-items-center ${tones[tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mt-2">{label}</div>
      <div className="text-lg sm:text-xl font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{value}</div>
    </div>
  );
};

export default StorePage;
