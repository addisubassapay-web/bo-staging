import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import confetti from "canvas-confetti";
import {
  TrendingUp, DollarSign, Package, Eye, Heart, Wallet, Clock,
  ArrowUpRight, Sparkles, Zap, Target, PartyPopper,
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

// -- Main page ---------------------------------------------------------------
const StoreAnalytics = () => {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!user) return;
    api.get("/seller/dashboard").then((r) => setData(r.data)).catch(() => {});
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
      <div className="rounded-2xl bg-gradient-to-r from-[#FF7A18] via-[#FF5B22] to-[#FF211F] text-white p-6 sm:p-8 shadow-sm">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div className="text-xs uppercase tracking-wider opacity-80">Seller dashboard</div>
            <h1 className="text-3xl sm:text-4xl font-extrabold mt-1">Hey, {user.username}</h1>
            <p className="text-white/90 mt-1">Here&apos;s how your store is performing right now.</p>
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
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="bg-white/15 backdrop-blur rounded-xl p-3">
            <div className="text-xs opacity-80">Today</div>
            <div className="text-xl font-bold">{money(t.today_earnings)}</div>
            <div className="text-[11px] opacity-80">{t.today_orders} orders</div>
          </div>
          <div className="bg-white/15 backdrop-blur rounded-xl p-3">
            <div className="text-xs opacity-80">30-day earnings</div>
            <div className="text-xl font-bold">{money(t.earnings_30d)}</div>
            <div className="text-[11px] opacity-80">{t.orders_30d} orders</div>
          </div>
          <div className="bg-white/15 backdrop-blur rounded-xl p-3">
            <div className="text-xs opacity-80">Wallet</div>
            <div className="text-xl font-bold">{money(t.wallet_balance)}</div>
            <div className="text-[11px] opacity-80">Available now</div>
          </div>
          <div className="bg-white/15 backdrop-blur rounded-xl p-3">
            <div className="text-xs opacity-80">Pending payout</div>
            <div className="text-xl font-bold">{money(t.pending_payout)}</div>
            <div className="text-[11px] opacity-80">{t.pending_payout > 0 ? "Processing" : "Nothing pending"}</div>
          </div>
        </div>
      </div>

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
    </div>
  );
};

export default StoreAnalytics;
