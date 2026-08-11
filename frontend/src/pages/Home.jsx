import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ArrowRight, ShieldCheck, Truck, Headphones, RotateCcw, Flame, Zap,
  CheckCircle2, Lock, Globe, Heart, Sparkles, Store as StoreIcon, BadgeCheck,
} from "lucide-react";

const money = (n) => `$${Number(n).toFixed(2)}`;

// -------------------- HERO CAROUSEL --------------------
const HERO_SLIDES = [
  {
    tag: "HOT DEALS",
    title: "Big Fashion Sale",
    subtitle: "Up to 50% OFF Premium Styles",
    img: "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=1600&auto=format&fit=crop&q=80",
    ctaLink: "/search?category_slug=women",
    accent: "from-rose-500/60 via-orange-400/40 to-transparent",
  },
  {
    tag: "NEW IN",
    title: "Electronics that spark joy",
    subtitle: "Verified sellers · Fast delivery",
    img: "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=1600&auto=format&fit=crop&q=80",
    ctaLink: "/search?category_slug=electronics",
    accent: "from-sky-500/60 via-indigo-400/30 to-transparent",
  },
  {
    tag: "TRENDING",
    title: "Vintage finds you'll love",
    subtitle: "One-of-a-kind pieces from real people",
    img: "https://images.unsplash.com/photo-1445205170230-053b83016050?w=1600&auto=format&fit=crop&q=80",
    ctaLink: "/search?category_slug=vintage",
    accent: "from-amber-500/60 via-orange-500/40 to-transparent",
  },
];

const HERO_HIGHLIGHTS = [
  { icon: ShieldCheck, label: "Buyer protection" },
  { icon: Truck,       label: "Fast delivery" },
  { icon: BadgeCheck,  label: "Verified sellers" },
  { icon: Heart,       label: "Loved by millions" },
];

const HeroCarousel = () => {
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % HERO_SLIDES.length), 5500);
    return () => clearInterval(t);
  }, [paused]);
  const s = HERO_SLIDES[idx];

  const now = new Date().getHours();
  const greeting = now < 12 ? "Good morning" : now < 18 ? "Good afternoon" : "Good evening";

  return (
    <section
      className="max-w-7xl mx-auto px-3 sm:px-4 pt-4 sm:pt-6"
      data-testid="hero-carousel"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {/* Warm welcome ribbon */}
      <div className="mb-3 sm:mb-4 flex items-center justify-between flex-wrap gap-2 px-1">
        <div className="flex items-center gap-2 text-sm sm:text-base">
          <span className="inline-flex h-6 sm:h-7 items-center gap-1.5 rounded-full bg-gradient-to-r from-[#FF7A18]/10 to-[#FF211F]/10 dark:from-[#FF7A18]/20 dark:to-[#FF211F]/20 border border-orange-200/70 dark:border-orange-500/30 px-2.5 text-[#FF211F] dark:text-orange-300 font-medium">
            <Sparkles className="h-3.5 w-3.5" /> {greeting}
          </span>
          <span className="text-neutral-500 dark:text-neutral-400 hidden sm:inline">— warm picks curated for you today</span>
        </div>
        <span className="text-xs text-neutral-500 dark:text-neutral-400 hidden md:inline">
          {HERO_SLIDES.length} featured stories · auto-rotates every few seconds
        </span>
      </div>

      <div
        className="relative rounded-2xl sm:rounded-3xl overflow-hidden aspect-[16/10] sm:aspect-[21/9] bg-gradient-to-br from-orange-100 via-rose-50 to-white dark:from-neutral-900 dark:via-neutral-900 dark:to-neutral-950 shadow-lg ring-1 ring-black/5 dark:ring-white/10"
      >
        {/* Background image with soft ken-burns */}
        <img
          key={s.img}
          src={s.img}
          alt={s.title}
          className="absolute inset-0 h-full w-full object-cover animate-hero-zoom will-change-transform"
        />

        {/* Warm brand overlay + per-slide accent */}
        <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-black/25 to-transparent" />
        <div className={`absolute inset-0 bg-gradient-to-br ${s.accent} mix-blend-soft-light`} />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_85%_25%,rgba(255,255,255,0.28),transparent_55%)]" />

        {/* Decorative blobs */}
        <div className="pointer-events-none absolute -top-16 -right-16 h-56 w-56 rounded-full bg-[#FF7A18]/40 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 left-1/3 h-56 w-56 rounded-full bg-[#FF211F]/30 blur-3xl" />

        {/* Content */}
        <div className="absolute inset-0 flex flex-col justify-center gap-3 sm:gap-4 p-5 sm:p-10 md:p-14 max-w-2xl">
          <span
            key={`${s.tag}-${idx}`}
            className="inline-flex items-center gap-1.5 self-start bg-white/95 text-[#FF211F] text-[10px] sm:text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full shadow-sm animate-hero-in"
          >
            <Flame className="h-3 w-3" /> {s.tag}
          </span>

          <h1
            key={`${s.title}-${idx}`}
            className="text-white text-3xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] tracking-tight drop-shadow-lg animate-hero-in"
          >
            {s.title}
          </h1>

          <p
            key={`${s.subtitle}-${idx}`}
            className="text-white/95 text-sm sm:text-lg max-w-md animate-hero-in"
          >
            {s.subtitle}
          </p>

          <div className="flex gap-2 sm:gap-3 flex-wrap">
            <Link to={s.ctaLink}>
              <Button
                className="bg-white text-[#FF211F] hover:bg-[#FF7A18] hover:text-white h-11 sm:h-12 px-5 sm:px-6 rounded-full font-semibold shadow-lg gap-2 transition-all group"
                data-testid="hero-shop-now"
              >
                Shop Now
                <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
              </Button>
            </Link>
            <Link to="/search">
              <Button
                variant="outline"
                className="h-11 sm:h-12 px-5 sm:px-6 rounded-full bg-white/10 backdrop-blur-sm border-2 border-white/70 text-white hover:bg-white hover:text-[#FF7A18] font-semibold"
              >
                Browse everything
              </Button>
            </Link>
          </div>

          {/* Trust chips (hidden on very small screens to keep hero clean) */}
          <div className="hidden sm:flex items-center gap-2 flex-wrap mt-2 sm:mt-3">
            {HERO_HIGHLIGHTS.map(({ icon: Icon, label }, i) => (
              <span
                key={label}
                className="inline-flex items-center gap-1.5 rounded-full bg-white/15 backdrop-blur-sm text-white text-xs font-medium px-3 py-1 ring-1 ring-white/20"
                data-testid={`hero-trust-chip-${i}`}
              >
                <Icon className="h-3.5 w-3.5" /> {label}
              </span>
            ))}
          </div>
        </div>

        {/* Slide dots */}
        <div className="absolute bottom-3 sm:bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5">
          {HERO_SLIDES.map((_, i) => (
            <button
              key={i}
              aria-label={`slide ${i + 1}`}
              onClick={() => setIdx(i)}
              className={`h-1.5 rounded-full transition-all ${
                i === idx ? "bg-white w-8 shadow" : "bg-white/60 w-2 hover:bg-white/80"
              }`}
            />
          ))}
        </div>
      </div>
    </section>
  );
};

// -------------------- FLASH DEALS COUNTDOWN --------------------
const useMidnightCountdown = (endsAtIso) => {
  const [t, setT] = useState(0);
  useEffect(() => {
    const tick = () => {
      if (!endsAtIso) {
        setT(6 * 3600);
        return;
      }
      const now = Date.now();
      const end = new Date(endsAtIso).getTime();
      setT(Math.max(0, Math.floor((end - now) / 1000)));
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [endsAtIso]);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return `${h}h ${m}m ${s}s`;
};

const FlashCard = ({ l, onFavChange, isFav }) => {
  // Prefer real backend flash-deal values; fall back to synthesized theatre for non-flash items.
  const seed = (l.id || "").split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const discount = l.flash_deal_discount_pct ?? 20 + (seed % 60);
  const stockLeft = 5 + (seed % 100);
  const original = (l.original_price && l.original_price > l.price)
    ? l.original_price
    : Number((l.price / (1 - discount / 100)).toFixed(2));
  const stockPct = Math.max(6, Math.min(95, stockLeft));

  return (
    <div className="group relative bg-white rounded-xl border border-neutral-200 overflow-hidden hover:shadow-lg hover:border-[#FF7A18]/40 transition" data-testid={`flash-card-${l.id}`}>
      <Link to={`/listing/${l.id}`}>
        <div className="relative aspect-square bg-neutral-100 overflow-hidden">
          <img src={l.images?.[0]} alt={l.title} className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-500" />
          <span className="absolute top-2 left-2 bg-[#FF211F] text-white text-[11px] font-bold px-2 py-1 rounded shadow">
            FLASH -{discount}%
          </span>
          <button
            aria-label="Favorite"
            onClick={(e) => { e.preventDefault(); onFavChange?.(l.id); }}
            className="absolute top-2 right-2 h-8 w-8 rounded-full bg-white/95 hover:bg-white grid place-items-center transition"
          >
            <Heart className={`h-4 w-4 ${isFav ? "fill-[#FF211F] text-[#FF211F]" : "text-neutral-600"}`} />
          </button>
        </div>
      </Link>
      <div className="p-3">
        <Link to={`/listing/${l.id}`}>
          <div className="text-sm font-medium text-neutral-900 line-clamp-2 min-h-[2.5rem]">{l.title}</div>
        </Link>
        <div className="mt-1.5 flex items-baseline gap-2 flex-wrap">
          <span className="text-lg font-bold text-neutral-900">{money(l.price)}</span>
          <span className="text-xs text-neutral-400 line-through">${Number(original).toFixed(2)}</span>
          <span className="ml-auto text-[11px] text-[#FF211F] font-medium">Only {stockLeft} left</span>
        </div>
        <div className="mt-2 h-1.5 rounded-full bg-neutral-100 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-[#FF211F] to-[#FF7A18]" style={{ width: `${stockPct}%` }} />
        </div>
        <div className="mt-2 text-[11px] text-amber-600 font-medium flex items-center gap-1">
          <Zap className="h-3 w-3" /> Fast Delivery
        </div>
      </div>
    </div>
  );
};

const FlashDeals = ({ items, onFav, favIds }) => {
  const endsAt = items?.[0]?.flash_deal_ends_at || null;
  const countdown = useMidnightCountdown(endsAt);
  if (!items?.length) return null;
  return (
    <section className="max-w-7xl mx-auto px-4 mt-10">
      <div className="bg-gradient-to-b from-[#FFF7EF] to-white rounded-2xl border border-orange-100 p-5 sm:p-6">
        <div className="flex items-start sm:items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-[#FF211F] flex items-center gap-2">
              <Zap className="h-6 w-6" /> Flash Deals
            </h2>
            <p className="text-sm text-neutral-600">Limited time offers — ends at midnight UTC</p>
          </div>
          <div className="bg-neutral-900 text-white px-4 py-2 rounded-full text-sm font-semibold" data-testid="flash-countdown">
            Ends in: <span className="text-orange-400 font-mono">{countdown}</span>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {items.map((l) => (
            <FlashCard key={l.id} l={l} isFav={favIds.has(l.id)} onFavChange={onFav} />
          ))}
        </div>
      </div>
    </section>
  );
};

// -------------------- TRUST STRIP --------------------
const TrustStrip = () => (
  <section className="max-w-7xl mx-auto px-4 mt-16 sm:mt-20">
    <div className="text-center">
      <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
        Why shop here
      </span>
      <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-neutral-900 dark:text-neutral-100 tracking-tight">Why millions trust us</h2>
      <p className="text-neutral-500 dark:text-neutral-400 mt-2">Safe shopping, worldwide, with buyer protection on every order.</p>
    </div>
    <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
      {[
        { icon: Lock, title: "Secure Payments", body: "Encrypted checkout & buyer protection", tone: "emerald" },
        { icon: Truck, title: "Fast Global Delivery", body: "Tracked shipping worldwide", tone: "sky" },
        { icon: RotateCcw, title: "Easy Returns", body: "7-30 day hassle-free returns", tone: "orange" },
        { icon: Headphones, title: "24/7 Support", body: "Instant help anytime you need", tone: "violet" },
      ].map((f, i) => {
        const tones = {
          emerald: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/15",
          sky:     "text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-500/15",
          orange:  "text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-500/15",
          violet:  "text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-500/15",
        };
        return (
          <div
            key={i}
            className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:shadow-[0_12px_28px_-16px_rgba(255,33,31,0.25)] hover:-translate-y-0.5 hover:border-[#FF7A18]/40 transition-all duration-300"
            data-testid={`trust-${i}`}
          >
            <div className={`h-11 w-11 rounded-xl grid place-items-center ${tones[f.tone]}`}>
              <f.icon className="h-5 w-5" />
            </div>
            <div className="font-semibold text-neutral-900 dark:text-neutral-100 mt-3.5">{f.title}</div>
            <div className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{f.body}</div>
          </div>
        );
      })}
    </div>
    <div className="mt-6 border-t border-neutral-200 dark:border-neutral-800 pt-5 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm text-neutral-600 dark:text-neutral-300">
      {["Verified Sellers", "Secure Checkout", "Global Shipping", "Buyer Protection"].map((t) => (
        <div key={t} className="flex items-center justify-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          <span>{t}</span>
        </div>
      ))}
    </div>
  </section>
);

// -------------------- CANT FIND PRODUCT CTA --------------------
const RequestBanner = () => (
  <section className="max-w-7xl mx-auto px-4 mt-16 sm:mt-20">
    <div className="relative rounded-3xl overflow-hidden bg-gradient-to-br from-[#FF7A18] via-[#FF5722] to-[#FF211F] text-white text-center px-6 py-14 shadow-[0_20px_50px_-20px_rgba(255,33,31,0.55)]">
      {/* Decorative blobs */}
      <div className="pointer-events-none absolute -top-16 -left-10 h-52 w-52 rounded-full bg-white/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-20 -right-16 h-64 w-64 rounded-full bg-black/20 blur-3xl" />
      <div className="relative">
        <div className="mx-auto h-14 w-14 rounded-2xl bg-white/20 backdrop-blur grid place-items-center mb-4 ring-1 ring-white/30">
          <Sparkles className="h-7 w-7" />
        </div>
        <h2 className="text-3xl sm:text-5xl font-extrabold tracking-tight">Can&apos;t Find Your Product?</h2>
        <p className="mt-3 text-white/90 max-w-2xl mx-auto text-sm sm:text-base">Send us your request and our team will source it for you from global suppliers.</p>
        <div className="mt-7 flex items-center justify-center gap-3 flex-wrap">
          <Link to="/chat">
            <Button className="bg-white text-[#FF211F] hover:bg-neutral-100 h-11 px-6 rounded-full font-semibold shadow-lg gap-1.5 group" data-testid="cta-request-product">
              Request Product <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
            </Button>
          </Link>
          <Link to="/chat">
            <Button variant="outline" className="h-11 px-6 rounded-full bg-white/10 backdrop-blur border-2 border-white/70 text-white hover:bg-white hover:text-[#FF7A18] font-semibold">
              Contact Support
            </Button>
          </Link>
        </div>
      </div>
    </div>
  </section>
);

// -------------------- FEATURE CARDS --------------------
const FeatureCards = () => (
  <section className="max-w-7xl mx-auto px-4 mt-14">
    <div className="grid md:grid-cols-3 gap-4">
      {[
        { icon: Headphones, title: "24/7 Customer Support", body: "Fast help from our support team anytime.", tone: "text-orange-500" },
        { icon: Truck, title: "Global Delivery", body: "Shipping to many countries worldwide.", tone: "text-orange-500" },
        { icon: ShieldCheck, title: "Buyer Protection", body: "Secure payments and trusted checkout.", tone: "text-orange-500" },
      ].map((f, i) => (
        <div key={i} className="bg-white border border-neutral-200 rounded-xl p-6" data-testid={`feature-${i}`}>
          <f.icon className={`h-9 w-9 ${f.tone}`} />
          <div className="mt-3 font-semibold text-lg text-neutral-900">{f.title}</div>
          <div className="text-sm text-neutral-500 mt-1">{f.body}</div>
        </div>
      ))}
    </div>
  </section>
);

// -------------------- FEATURED STORES STRIP --------------------
const TIER_META = {
  gold:   { label: "Gold Verified",   ring: "ring-amber-300",   pill: "bg-amber-100 text-amber-800 border-amber-200" },
  silver: { label: "Silver Verified", ring: "ring-slate-300",   pill: "bg-slate-100 text-slate-700 border-slate-200" },
  bronze: { label: "Bronze Verified", ring: "ring-orange-300",  pill: "bg-orange-100 text-orange-800 border-orange-200" },
  none:   { label: "New store",       ring: "ring-neutral-200", pill: "bg-neutral-100 text-neutral-600 border-neutral-200" },
};

const FeaturedStoresStrip = ({ stores }) => {
  if (!stores || stores.length === 0) return null;
  return (
    <section className="max-w-7xl mx-auto px-4 mt-14" data-testid="featured-stores-section">
      <div className="flex items-end justify-between mb-4 gap-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <StoreIcon className="h-6 w-6 text-[#FF7A18]" /> Featured Storefronts
          </h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Handpicked sellers you&apos;ll love</p>
        </div>
        <Link to="/search" className="text-sm text-[#FF7A18] font-medium hover:underline flex items-center gap-1 whitespace-nowrap">
          Discover more <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      <div className="flex gap-4 overflow-x-auto pb-2 -mx-4 px-4 snap-x snap-mandatory scrollbar-hide" data-testid="featured-stores-strip">
        {stores.map((s) => {
          const tier = TIER_META[s.verified_tier] || TIER_META.none;
          return (
            <Link
              key={s.id}
              to={`/store/${s.slug}`}
              className="snap-start shrink-0 w-64 group"
              data-testid={`featured-store-${s.slug}`}
            >
              <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden hover:shadow-lg hover:border-[#FF7A18] transition h-full">
                <div className="h-24 bg-gradient-to-br from-[#FF7A18] via-[#FF5B22] to-[#FF211F] relative">
                  {s.banner && (
                    <img src={s.banner} alt="" className="absolute inset-0 h-full w-full object-cover opacity-70" />
                  )}
                </div>
                <div className="p-4 -mt-8">
                  <div className={`h-14 w-14 rounded-full bg-white dark:bg-neutral-900 ring-4 ${tier.ring} grid place-items-center overflow-hidden shadow`}>
                    {s.logo ? (
                      <img src={s.logo} alt={s.name} className="h-full w-full object-cover" />
                    ) : (
                      <StoreIcon className="h-6 w-6 text-neutral-500" />
                    )}
                  </div>
                  <div className="mt-3 flex items-center gap-1.5">
                    <div className="font-bold text-neutral-900 dark:text-neutral-100 truncate group-hover:text-[#FF211F] transition">
                      {s.name}
                    </div>
                    {s.verified_tier !== "none" && <BadgeCheck className="h-4 w-4 text-[#FF7A18] shrink-0" />}
                  </div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1">
                    {s.tagline || `/${s.slug}`}
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[11px]">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border ${tier.pill}`}>
                      {tier.label}
                    </span>
                    <span className="text-neutral-500 dark:text-neutral-400 tabular-nums">
                      {s.total_sales} sales
                    </span>
                  </div>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
};

// -------------------- MAIN PAGE --------------------
const Home = () => {
  const [flash, setFlash] = useState([]);
  const [recent, setRecent] = useState([]);
  const [trending, setTrending] = useState([]);
  const [forYou, setForYou] = useState([]);
  const [recentlyViewed, setRecentlyViewed] = useState([]);
  const [shelves, setShelves] = useState([]);
  const [featuredStores, setFeaturedStores] = useState([]);
  const [favIds, setFavIds] = useState(new Set());

  useEffect(() => {
    api.get("/flash-deals", { params: { limit: 10 } }).then((r) => setFlash(r.data)).catch(() => {});
    api.get("/listings", { params: { sort: "newest", limit: 12 } }).then((r) => setRecent(r.data)).catch(() => {});
    api.get("/listings", { params: { sort: "trending", limit: 12 } }).then((r) => setTrending(r.data)).catch(() => {});
    api.get("/shelves").then((r) => setShelves(r.data)).catch(() => {});
    api.get("/stores-featured", { params: { limit: 12 } }).then((r) => setFeaturedStores(r.data)).catch(() => {});
    const token = localStorage.getItem("mercari_token");
    if (token) {
      api.get("/favorites").then((r) => setFavIds(new Set(r.data.map((l) => l.id)))).catch(() => {});
      api.get("/for-you", { params: { limit: 12 } }).then((r) => setForYou(r.data)).catch(() => {});
      api.get("/recently-viewed", { params: { limit: 12 } }).then((r) => setRecentlyViewed(r.data)).catch(() => {});
    }
  }, []);

  const toggleFav = async (id) => {
    const token = localStorage.getItem("mercari_token");
    if (!token) { window.location.href = "/login"; return; }
    const isFav = favIds.has(id);
    try {
      if (isFav) { await api.delete(`/favorites/${id}`); }
      else { await api.post(`/favorites/${id}`); }
      setFavIds((prev) => { const s = new Set(prev); isFav ? s.delete(id) : s.add(id); return s; });
    } catch { /* no-op */ }
  };

  const flashItems = useMemo(() => (flash.length ? flash : recent).slice(0, 10), [flash, recent]);

  return (
    <div className="bg-white dark:bg-neutral-950">
      <HeroCarousel />

      {/* Recently Viewed (only for logged-in users with history) */}
      {recentlyViewed.length > 0 && (
        <section className="max-w-7xl mx-auto px-4 mt-8" data-testid="recently-viewed-section">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-lg sm:text-xl font-bold text-neutral-900">Pick up where you left off</h2>
              <p className="text-xs text-neutral-500">Recently viewed</p>
            </div>
            <Link to="/search" className="text-xs text-[#FF7A18] font-medium hover:underline">Browse more</Link>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-6 gap-3">
            {recentlyViewed.slice(0, 12).map((l) => (
              <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={(id, isFav) => setFavIds((prev) => { const s = new Set(prev); isFav ? s.add(id) : s.delete(id); return s; })} />
            ))}
          </div>
        </section>
      )}

      {/* Limited time badge */}
      <div className="max-w-7xl mx-auto px-4 mt-10 text-center">
        <Badge className="bg-[#FF7A18] hover:bg-[#FF7A18] text-white uppercase tracking-wider font-bold px-4 py-1">Limited Time Deals</Badge>
      </div>

      <FlashDeals items={flashItems} onFav={toggleFav} favIds={favIds} />

      {/* For You — personalised */}
      {forYou.length > 0 && (
        <section className="max-w-7xl mx-auto px-4 mt-14" data-testid="for-you-section">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-2xl sm:text-3xl font-bold text-neutral-900 flex items-center gap-2">
                <Sparkles className="h-6 w-6 text-[#FF7A18]" /> For You
              </h2>
              <p className="text-sm text-neutral-500">Handpicked from your favourites &amp; purchases</p>
            </div>
            <Link to="/search" className="text-sm text-[#FF7A18] font-medium hover:underline flex items-center gap-1">
              Refresh <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {forYou.slice(0, 12).map((l) => (
              <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={(id, isFav) => setFavIds((prev) => { const s = new Set(prev); isFav ? s.add(id) : s.delete(id); return s; })} />
            ))}
          </div>
        </section>
      )}

      <TrustStrip />

      <FeaturedStoresStrip stores={featuredStores} />

      {/* Category Shelves */}
      {shelves.length > 0 && (
        <section className="max-w-7xl mx-auto px-4 mt-16 space-y-12" data-testid="category-shelves">
          {shelves.map((sh) => (
            <div key={sh.id}>
              <div className="flex items-end justify-between mb-5 gap-4">
                <div>
                  <h2 className="text-xl sm:text-2xl font-extrabold text-neutral-900 dark:text-neutral-100 tracking-tight">{sh.title}</h2>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{sh.subtitle}</p>
                </div>
                <Link
                  to={`/search?category_slug=${sh.category_slugs[0]}`}
                  className="text-sm text-[#FF7A18] font-semibold hover:text-[#FF211F] transition flex items-center gap-1 whitespace-nowrap group"
                  data-testid={`shelf-see-${sh.id}`}
                >
                  See all <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-8 gap-3 sm:gap-4">
                {sh.listings.slice(0, 8).map((l) => (
                  <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={(id, isFav) => setFavIds((prev) => { const s = new Set(prev); isFav ? s.add(id) : s.delete(id); return s; })} />
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Trending Now */}
      <section className="max-w-7xl mx-auto px-4 mt-16 sm:mt-20">
        <div className="flex items-end justify-between mb-6 gap-4">
          <div>
            <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF211F] bg-[#FF211F]/10 border border-[#FF211F]/20 rounded-full px-3 py-1">
              Live now
            </span>
            <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold text-[#FF211F] flex items-center gap-2 tracking-tight">
              <Flame className="h-6 w-6" /> Trending Now
            </h2>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">Based on popularity &amp; engagement</p>
          </div>
          <Link to="/search?sort=trending" className="text-sm text-[#FF7A18] font-semibold hover:text-[#FF211F] transition flex items-center gap-1 whitespace-nowrap group">
            Live Feed <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3 sm:gap-4">
          {trending.slice(0, 12).map((l) => (
            <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={(id, isFav) => setFavIds((prev) => { const s = new Set(prev); isFav ? s.add(id) : s.delete(id); return s; })} />
          ))}
        </div>
      </section>

      {/* Just listed */}
      {recent.length > 0 && (
        <section className="max-w-7xl mx-auto px-4 mt-16 sm:mt-20">
          <div className="flex items-end justify-between mb-6 gap-4">
            <div>
              <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-full px-3 py-1">
                Fresh drops
              </span>
              <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold text-neutral-900 dark:text-neutral-100 tracking-tight">Just listed</h2>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">The latest items on Mercari Global</p>
            </div>
            <Link to="/search?sort=newest" className="text-sm text-[#FF7A18] font-semibold hover:text-[#FF211F] transition flex items-center gap-1 whitespace-nowrap group">
              View more <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3 sm:gap-4">
            {recent.slice(0, 12).map((l) => (
              <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={(id, isFav) => setFavIds((prev) => { const s = new Set(prev); isFav ? s.add(id) : s.delete(id); return s; })} />
            ))}
          </div>
        </section>
      )}

      <RequestBanner />
      <FeatureCards />

      <div className="h-14" />
    </div>
  );
};

export default Home;
