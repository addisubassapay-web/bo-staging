import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import confetti from "canvas-confetti";
import {
  TrendingUp, DollarSign, Package, Eye, Heart, Wallet, Clock,
  ArrowUpRight, Sparkles, Zap, Target, PartyPopper, TrendingDown, Trophy, Plus, PackagePlus, Rocket, Store as StoreIcon,
} from "lucide-react";

const money = (n) => `$${Number(n || 0).toFixed(2)}`;

// -- Progress ring (SVG) -----------------------------------------------------
const ProgressRing = ({ pct = 0, size = 88, stroke = 8 }) => {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c - (Math.min(100, Math.max(0, pct)) / 100) * c;
  return (
    <div className="relative" style={{ width: size, height: size }} data-testid="weekly-progress-ring">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.25)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          stroke="white" strokeWidth={stroke} fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={off}
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-white">
        <div className="text-center leading-tight">
          <div className="text-lg font-bold">{Math.round(pct)}%</div>
          <div className="text-[9px] uppercase tracking-wider opacity-80">of goal</div>
        </div>
      </div>
    </div>
  );
};

// -- Sparkline chart (pure SVG, no library) -----------------------------------
const Sparkline = ({ series }) => {
  if (!series || series.length === 0) return null;
  const w = 640, h = 180, padX = 8, padY = 20;
  const vals = series.map((s) => s.earnings);
  const max = Math.max(1, ...vals);
  const step = (w - padX * 2) / Math.max(1, series.length - 1);
  const pts = series.map((s, i) => {
    const x = padX + i * step;
    const y = h - padY - (s.earnings / max) * (h - padY * 2);
    return [x, y];
  });
  const path = pts.map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`)).join(" ");
  const area = `${path} L ${pts[pts.length - 1][0]} ${h} L ${pts[0][0]} ${h} Z`;
  const last = series[series.length - 1];
  return (
    <div className="relative" data-testid="earnings-sparkline">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-40">
        <defs>
          <linearGradient id="sparkFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#FF7A18" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#FF7A18" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#sparkFill)" />
        <path d={path} fill="none" stroke="#FF211F" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={i === pts.length - 1 ? 4 : 0} fill="#FF211F" />
        ))}
      </svg>
      <div className="absolute top-1 right-2 text-xs bg-white/95 border border-neutral-200 rounded-full px-2 py-0.5 font-medium">
        Today: <span className="text-[#FF211F]">{money(last?.earnings)}</span>
      </div>
    </div>
  );
};

// -- Stat cards --------------------------------------------------------------
const StatCard = ({ icon: Icon, label, value, sub, tone = "orange", testid }) => {
  const tones = {
    orange: "from-orange-100 to-orange-50 text-orange-700 ring-orange-100",
    emerald: "from-emerald-100 to-emerald-50 text-emerald-700 ring-emerald-100",
    sky: "from-sky-100 to-sky-50 text-sky-700 ring-sky-100",
    violet: "from-violet-100 to-violet-50 text-violet-700 ring-violet-100",
  };
  return (
    <div className="bg-white border border-neutral-200 rounded-2xl p-5 hover:shadow-md transition" data-testid={testid}>
      <div className={`h-10 w-10 rounded-xl bg-gradient-to-br ${tones[tone]} ring-1 grid place-items-center`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="mt-3 text-xs uppercase tracking-wider text-neutral-500 font-medium">{label}</div>
      <div className="mt-1 text-2xl font-bold text-neutral-900">{value}</div>
      {sub && <div className="text-xs text-neutral-500 mt-1">{sub}</div>}
    </div>
  );
};

// -- Weekly Recap Card ------------------------------------------------------
const WeeklyRecapCard = ({ recap, currentEarnings = 0 }) => {
  const hasData = (recap.earnings || 0) > 0 || (recap.orders || 0) > 0;
  const delta = recap.delta_pct_vs_current || 0;
  const trendingUp = delta >= 0;
  const weekLabel = recap.week_start
    ? new Date(recap.week_start).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "";

  return (
    <div
      className="mt-6 rounded-2xl border border-neutral-200 bg-white overflow-hidden"
      data-testid="weekly-recap-card"
    >
      <div className="grid md:grid-cols-[minmax(0,1fr)_320px]">
        {/* Left: recap summary */}
        <div className="p-5 sm:p-6">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-neutral-500 font-medium">
            <Trophy className="h-4 w-4 text-[#FF7A18]" /> Weekly recap
            {weekLabel && <span className="text-neutral-400 normal-case tracking-normal">· week of {weekLabel}</span>}
          </div>

          {!hasData ? (
            <div className="mt-4 text-neutral-600" data-testid="weekly-recap-empty">
              <div className="text-lg font-bold text-neutral-900">No sales last week</div>
              <div className="text-sm mt-1">{recap.suggestion || "List a fresh item this week to attract new shoppers."}</div>
            </div>
          ) : (
            <>
              <div className="mt-3 flex items-baseline gap-3 flex-wrap">
                <div className="text-3xl sm:text-4xl font-extrabold text-neutral-900" data-testid="recap-earnings">
                  {money(recap.earnings)}
                </div>
                <div className={`inline-flex items-center gap-1 text-sm font-medium rounded-full px-2 py-0.5 ${
                  trendingUp
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-rose-50 text-rose-700 border border-rose-200"
                }`}
                data-testid="recap-delta"
                >
                  {trendingUp ? <ArrowUpRight className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                  {trendingUp ? "+" : ""}{delta}% vs this week
                </div>
              </div>
              <div className="text-sm text-neutral-500 mt-1">
                <span className="font-medium text-neutral-700" data-testid="recap-orders">{recap.orders}</span> orders shipped ·
                <span className="ml-1">This week so far: <span className="font-medium text-neutral-700">{money(currentEarnings)}</span></span>
              </div>

              <div className="mt-4 rounded-xl bg-gradient-to-r from-[#FFF7EF] to-white border border-orange-100 p-3 flex items-start gap-2">
                <Sparkles className="h-4 w-4 text-[#FF7A18] mt-0.5 shrink-0" />
                <p className="text-sm text-neutral-700" data-testid="recap-suggestion">{recap.suggestion}</p>
              </div>
            </>
          )}
        </div>

        {/* Right: top product */}
        <div className="bg-gradient-to-br from-neutral-50 to-white border-t md:border-t-0 md:border-l border-neutral-200 p-5 sm:p-6">
          <div className="text-xs uppercase tracking-wider text-neutral-500 font-medium">Top seller last week</div>
          {recap.top_product ? (
            <Link
              to={`/listing/${recap.top_product.id}`}
              className="mt-3 flex gap-3 group"
              data-testid="recap-top-product"
            >
              <img
                src={recap.top_product.images?.[0]}
                alt={recap.top_product.title}
                className="h-20 w-20 rounded-xl object-cover bg-neutral-100 shrink-0"
              />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-neutral-900 line-clamp-2 group-hover:text-[#FF211F] transition">
                  {recap.top_product.title}
                </div>
                <div className="text-base font-bold text-[#FF211F] mt-1">{money(recap.top_product.price)}</div>
                <div className="text-[11px] text-neutral-500 mt-1">Tap to view listing</div>
              </div>
            </Link>
          ) : (
            <div className="mt-3 text-sm text-neutral-500" data-testid="recap-no-top-product">
              Once you close orders, your best seller will appear here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// -- Main page ---------------------------------------------------------------
const StoreAnalytics = () => {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState(null);
  const [latestPublished, setLatestPublished] = useState([]);
  const [myStoreSlug, setMyStoreSlug] = useState(null);
  const [discoveries, setDiscoveries] = useState({ items: [], total: 0 });

  useEffect(() => {
    if (!user) return;
    api.get("/seller/dashboard").then((r) => setData(r.data)).catch(() => {});
    api.get("/store/analytics/category-discoveries", { params: { days: 7 } })
      .then((r) => setDiscoveries(r.data || { items: [], total: 0 }))
      .catch(() => {});
    api.get("/my/store").then((r) => {
      const slug = r.data?.slug;
      setMyStoreSlug(slug || null);
      if (slug) {
        api.get(`/stores/${slug}/listings`).then((res) => {
          const sorted = [...(res.data || [])].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
          setLatestPublished(sorted.slice(0, 8));
        }).catch(() => {});
      }
    }).catch(() => {});
  }, [user]);

  // NOTE: the milestone-based celebrations useEffect above replaces the older 100%-only handler.

  if (authLoading) return <div className="max-w-5xl mx-auto px-4 py-16 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="text-neutral-700">Please <Link to="/login" className="text-[#FF7A18] underline">log in</Link> to view your dashboard.</p>
      </div>
    );
  }
  if (!data) return <div className="max-w-5xl mx-auto px-4 py-16 text-neutral-500">Loading dashboard…</div>;

  const t = data.totals;
  return (
    <div className="max-w-7xl mx-auto px-4 py-8" data-testid="seller-dashboard">
      {(data.weekly?.progress_pct || 0) >= 100 && (
        <div className="mb-4 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 text-white px-5 py-4 flex items-center gap-3 shadow-md" data-testid="goal-hit-banner">
          <PartyPopper className="h-6 w-6" />
          <div className="flex-1">
            <div className="font-bold">Goal hit! You earned {money(data.weekly?.earned)} this week.</div>
            <div className="text-sm text-emerald-50">Time to raise the bar — set a new weekly target from the ring on the right.</div>
          </div>
        </div>
      )}
      {/* Header banner */}
      <div className="relative rounded-3xl bg-gradient-to-br from-[#FF7A18] via-[#FF3D66] to-[#7C3AED] text-white p-6 sm:p-8 shadow-xl overflow-hidden">
        <div className="pointer-events-none absolute -top-16 -right-10 h-64 w-64 rounded-full bg-white/20 blur-3xl animate-pulse" />
        <div className="pointer-events-none absolute -bottom-20 left-1/4 h-72 w-72 rounded-full bg-amber-300/30 blur-3xl" />
        <div className="pointer-events-none absolute top-1/3 -left-10 h-40 w-40 rounded-full bg-fuchsia-400/30 blur-3xl" />
        <div className="relative flex items-start justify-between flex-wrap gap-3">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] opacity-90 font-semibold">Seller dashboard</div>
            <h1 className="text-3xl sm:text-4xl font-extrabold mt-1 tracking-tight">Hey, {user.username}</h1>
            <p className="text-white/90 mt-1">Here&apos;s how your store is performing right now.</p>
            {/* Quick action buttons */}
            <div className="mt-4 flex gap-2 flex-wrap">
              <Link to="/sell">
                <Button className="min-h-[44px] rounded-full bg-white text-[#FF211F] hover:bg-neutral-100 font-semibold gap-1.5 shadow-md" data-testid="dash-cta-new-listing">
                  <PackagePlus className="h-4 w-4" /> New listing
                </Button>
              </Link>
              <Link to="/sell">
                <Button className="min-h-[44px] rounded-full bg-white/20 hover:bg-white/30 text-white border border-white/40 backdrop-blur gap-1.5" data-testid="dash-cta-resell">
                  <Rocket className="h-4 w-4" /> Bulk resell
                </Button>
              </Link>
              {myStoreSlug && (
                <Link to={`/store/${myStoreSlug}`}>
                  <Button className="min-h-[44px] rounded-full bg-white/20 hover:bg-white/30 text-white border border-white/40 backdrop-blur gap-1.5" data-testid="dash-cta-view-store">
                    <StoreIcon className="h-4 w-4" /> View my store
                  </Button>
                </Link>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <div className="text-xs opacity-80 flex items-center justify-end gap-1"><Target className="h-3 w-3" /> Weekly goal</div>
              <button
                onClick={async () => {
                  const v = prompt("Weekly earnings goal (USD)", String(data.weekly?.goal || 0));
                  if (v == null) return;
                  const num = parseFloat(v);
                  if (isNaN(num) || num < 0) return;
                  try {
                    await api.put("/seller/goal", { weekly_earnings_goal: num });
                    const r = await api.get("/seller/dashboard");
                    setData(r.data);
                  } catch { /* ignore */ }
                }}
                className="text-lg font-bold underline decoration-white/30 hover:decoration-white"
                data-testid="edit-weekly-goal"
              >
                {money(data.weekly?.goal || 0)}
              </button>
              <div className="text-[11px] opacity-80">Earned {money(data.weekly?.earned || 0)} this week</div>
            </div>
            <ProgressRing pct={data.weekly?.progress_pct || 0} />
          </div>
        </div>
        <div className="relative mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          <div className="bg-white/15 backdrop-blur rounded-xl p-3 border border-white/20">
            <div className="text-xs opacity-80">Today</div>
            <div className="text-xl font-bold tabular-nums">{money(t.today_earnings)}</div>
            <div className="text-[11px] opacity-80">{t.today_orders} orders</div>
          </div>
          <div className="bg-white/15 backdrop-blur rounded-xl p-3 border border-white/20">
            <div className="text-xs opacity-80">30-day earnings</div>
            <div className="text-xl font-bold tabular-nums">{money(t.earnings_30d)}</div>
            <div className="text-[11px] opacity-80">{t.orders_30d} orders</div>
          </div>
          <div className="bg-white/15 backdrop-blur rounded-xl p-3 border border-white/20">
            <div className="text-xs opacity-80">Wallet</div>
            <div className="text-xl font-bold tabular-nums">{money(t.wallet_balance)}</div>
            <div className="text-[11px] opacity-80">Available now</div>
          </div>
          <div className="bg-white/15 backdrop-blur rounded-xl p-3 border border-white/20">
            <div className="text-xs opacity-80">Pending payout</div>
            <div className="text-xl font-bold tabular-nums">{money(t.pending_payout)}</div>
            <div className="text-[11px] opacity-80">{t.pending_payout > 0 ? "Processing" : "Nothing pending"}</div>
          </div>
        </div>
      </div>

      {/* Recently published — proves auto-attach to store works */}
      {latestPublished.length > 0 && (
        <div className="mt-6 rounded-2xl border border-neutral-200 bg-white p-5" data-testid="latest-published-strip">
          <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 grid place-items-center shadow-sm">
                <Sparkles className="h-4 w-4 text-white" />
              </div>
              <div>
                <h2 className="font-bold text-neutral-900">Recently published in your store</h2>
                <p className="text-xs text-neutral-500">Every new listing lands here — and in your storefront — instantly.</p>
              </div>
            </div>
            {myStoreSlug && (
              <Link to={`/store/${myStoreSlug}`} className="text-xs font-semibold text-[#FF7A18] hover:underline">View all →</Link>
            )}
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory -mx-5 px-5">
            {latestPublished.slice(0, 8).map((l) => (
              <Link key={l.id} to={`/listing/${l.id}`} className="snap-start shrink-0 w-[40%] sm:w-[160px] group">
                <div className="rounded-xl overflow-hidden border border-neutral-200 group-hover:border-[#FF211F] transition">
                  <div className="aspect-square bg-neutral-100 overflow-hidden">
                    {(l.images?.[0]) && <img src={l.images[0]} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform" />}
                  </div>
                  <div className="p-2">
                    <div className="text-xs font-medium text-neutral-800 line-clamp-1">{l.title}</div>
                    <div className="text-sm font-bold text-[#FF211F] tabular-nums">{money(l.price)}</div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Earnings chart */}
      <div className="mt-6 bg-white border border-neutral-200 rounded-2xl p-5">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2"><TrendingUp className="h-5 w-5 text-[#FF7A18]" /> Earnings — last 30 days</h2>
            <p className="text-sm text-neutral-500">Net of platform fees. Points show daily net earnings.</p>
          </div>
          <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200"><ArrowUpRight className="h-3 w-3 mr-1" /> Live</Badge>
        </div>
        <div className="mt-4">
          <Sparkline series={data.series} />
        </div>
      </div>

      {/* Weekly Recap */}
      {data.weekly_recap && (
        <WeeklyRecapCard recap={data.weekly_recap} currentEarnings={data.weekly?.earned || 0} />
      )}

      {/* Stat grid */}
      <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={Package} label="Active listings" value={data.listings.active} sub={`${data.listings.sold} sold total`} tone="orange" testid="stat-active" />
        <StatCard icon={Zap} label="Flash deals live" value={data.listings.flash} sub="Auto-rotated daily" tone="sky" testid="stat-flash" />
        <StatCard icon={Eye} label="Impressions" value={data.engagement.views.toLocaleString()} sub={`${data.engagement.likes.toLocaleString()} likes`} tone="violet" testid="stat-impressions" />
        <StatCard icon={DollarSign} label="Wallet" value={money(t.wallet_balance)} sub={t.pending_payout > 0 ? `+ ${money(t.pending_payout)} pending` : "—"} tone="emerald" testid="stat-wallet" />
      </div>

      {/* Recent orders */}
      <div className="mt-6 grid md:grid-cols-[1fr_320px] gap-6">
        <div className="bg-white border border-neutral-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold flex items-center gap-2"><Clock className="h-5 w-5 text-[#FF7A18]" /> Latest orders</h2>
            <Link to="/profile?tab=sales" className="text-sm text-[#FF7A18] hover:underline">See all</Link>
          </div>
          {data.recent_orders.length === 0 ? (
            <div className="text-sm text-neutral-500 py-6 text-center">No sales yet. List an item to get started.</div>
          ) : (
            <div className="divide-y divide-neutral-100">
              {data.recent_orders.map((o) => (
                <div key={o.id} className="py-3 flex items-center gap-3">
                  <img src={o.listing_image} alt="" className="h-12 w-12 rounded-lg object-cover bg-neutral-100" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-neutral-900 line-clamp-1">{o.listing_title}</div>
                    <div className="text-xs text-neutral-500">
                      {o.buyer_name} · {new Date(o.created_at).toLocaleDateString()} · <span className="capitalize">{o.status}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-emerald-600">+{money(o.amount)}</div>
                    <div className="text-[11px] text-neutral-400 font-mono">#{o.id.slice(0, 6)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="bg-white border border-neutral-200 rounded-2xl p-5" data-testid="category-discoveries-card">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-bold">
                <Target className="h-5 w-5 text-[#2563EB]" /> Discoveries by category
              </div>
              <span className="text-xs text-neutral-400">last 7 days</span>
            </div>
            <p className="text-xs text-neutral-500 mt-1">Buyers who opened your store from a category filter in the directory.</p>
            {discoveries.total === 0 ? (
              <div className="mt-4 rounded-xl bg-neutral-50 border border-dashed border-neutral-200 p-4 text-center text-sm text-neutral-500">
                No category-driven visits yet.
                <div className="text-xs mt-1">Tag your store with up to 3 categories in <Link to="/store/manage" className="text-[#2563EB] underline">Store settings</Link> to be discoverable.</div>
              </div>
            ) : (
              <ul className="mt-3 space-y-2" data-testid="category-discoveries-list">
                {discoveries.items.map((d) => {
                  const pct = discoveries.total > 0 ? Math.round((d.count / discoveries.total) * 100) : 0;
                  return (
                    <li key={d.category_id} className="text-sm" data-testid={`cat-discovery-${d.slug || d.category_id}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-neutral-800">{d.name}</span>
                        <span className="tabular-nums text-neutral-500 text-xs">{d.count} buyer{d.count === 1 ? "" : "s"}</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-neutral-100 overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-[#7DD3FC] to-[#2563EB]" style={{ width: `${Math.max(6, pct)}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="mt-3 pt-3 border-t border-neutral-100 flex items-center justify-between text-xs">
              <span className="text-neutral-500">Total this week</span>
              <span className="font-semibold text-neutral-800 tabular-nums">{discoveries.total}</span>
            </div>
          </div>

          <div className="bg-gradient-to-br from-[#FFF7EF] to-white border border-orange-100 rounded-2xl p-5">
            <div className="flex items-center gap-2 text-[#FF211F] font-bold">
              <Sparkles className="h-5 w-5" /> Pro tips
            </div>
            <ul className="mt-3 space-y-2 text-sm text-neutral-700">
              <li>• Enhance photos with AI for a 2x higher click-through</li>
              <li>• Reply to messages within 1 hour to boost your rating</li>
              <li>• Verified sellers show a gold badge across the platform</li>
            </ul>
            <Link to="/verify"><Button variant="outline" className="mt-4 w-full border-[#FF7A18] text-[#FF7A18] hover:bg-[#FFF3F2]">Get verified →</Button></Link>
          </div>
          <div className="bg-white border border-neutral-200 rounded-2xl p-5">
            <div className="flex items-center gap-2 font-bold">
              <Wallet className="h-5 w-5 text-emerald-600" /> Cash out
            </div>
            <p className="text-sm text-neutral-500 mt-1">Move your earnings to your bank once your wallet is above $10.</p>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-2xl font-bold">{money(t.wallet_balance)}</span>
              <span className="text-xs text-neutral-500">available</span>
            </div>
            <Link to="/wallet"><Button className="mt-3 w-full bg-emerald-600 hover:bg-emerald-700">Withdraw</Button></Link>
          </div>
        </div>
      </div>

      {/* Floating quick-action — mobile-friendly */}
      <Link to="/sell" className="fixed bottom-6 right-6 z-40 sm:hidden" data-testid="dash-fab-new">
        <div className="h-14 w-14 rounded-full bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white shadow-2xl grid place-items-center hover:scale-105 active:scale-95 transition-transform">
          <Plus className="h-6 w-6" />
        </div>
      </Link>
    </div>
  );
};

export default StoreAnalytics;
