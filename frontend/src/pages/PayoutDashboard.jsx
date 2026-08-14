import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { Button } from "@/components/ui/button";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from "recharts";
import {
  Snowflake, Wallet as WalletIcon, Clock, TrendingUp, ArrowUpRight, Package as PackageIcon,
  CalendarClock, ChevronLeft,
} from "lucide-react";

const WINDOWS = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
  { days: 180, label: "6mo" },
];

const dayLabel = (iso) => {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const StatCard = ({ icon: Icon, label, value, sub, tone = "neutral", testid }) => {
  const tones = {
    neutral: "from-neutral-100 to-neutral-50 text-neutral-800 dark:from-neutral-800 dark:to-neutral-900 dark:text-neutral-100 border-neutral-200 dark:border-neutral-800",
    green: "from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-500/25 border-transparent",
    amber: "from-amber-400 to-orange-500 text-white shadow-lg shadow-amber-500/25 border-transparent",
    red: "from-[#FF7A18] to-[#FF211F] text-white shadow-lg shadow-[#FF211F]/25 border-transparent",
    blue: "from-sky-500 to-indigo-500 text-white shadow-lg shadow-sky-500/25 border-transparent",
  };
  return (
    <div className={`rounded-2xl border p-5 bg-gradient-to-br ${tones[tone]}`} data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-[0.2em] font-semibold opacity-80">{label}</span>
        <Icon className="h-4 w-4 opacity-80" />
      </div>
      <div className="mt-2 text-3xl font-extrabold tabular-nums">{value}</div>
      {sub && <div className="text-xs opacity-80 mt-1">{sub}</div>}
    </div>
  );
};

const PayoutDashboard = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { format } = useCurrency();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    setLoading(true);
    api
      .get("/wallet/payout-dashboard", { params: { days } })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [days, user, authLoading, navigate]);

  const chartData = useMemo(
    () => (data?.timeline || []).map((row) => ({
      ...row,
      dateLabel: dayLabel(row.date),
    })),
    [data],
  );

  const daysLeft = useMemo(() => {
    const iso = data?.next_release?.estimated_delivery_at;
    if (!iso) return null;
    const then = new Date(iso);
    return Math.max(0, Math.ceil((then - new Date()) / (1000 * 60 * 60 * 24)));
  }, [data]);

  if (loading || !data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-10">
        <div className="h-8 w-40 bg-neutral-100 dark:bg-neutral-800 animate-pulse rounded-full mb-4" />
        <div className="grid md:grid-cols-4 gap-4 mb-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-32 bg-neutral-100 dark:bg-neutral-800 animate-pulse rounded-2xl" />
          ))}
        </div>
        <div className="h-72 bg-neutral-100 dark:bg-neutral-800 animate-pulse rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8" data-testid="payout-dashboard">
      {/* Header */}
      <div className="mb-8 flex items-end justify-between flex-wrap gap-3">
        <div>
          <Link to="/wallet" className="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-[#FF211F] transition mb-2">
            <ChevronLeft className="h-4 w-4" /> Back to wallet
          </Link>
          <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
            Seller payouts
          </span>
          <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
            Payout dashboard
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Track available cash, frozen sales, and pending withdrawals across time.
          </p>
        </div>
        <div className="inline-flex bg-neutral-100 dark:bg-neutral-800 rounded-full p-1" data-testid="window-picker">
          {WINDOWS.map((w) => (
            <button
              key={w.days}
              onClick={() => setDays(w.days)}
              className={`px-3 h-8 rounded-full text-xs font-semibold transition ${days === w.days ? "bg-white dark:bg-neutral-900 text-[#FF211F] shadow-sm" : "text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"}`}
              data-testid={`window-${w.days}`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {/* Balance cards */}
      <div className="grid md:grid-cols-4 gap-3 sm:gap-4 mb-8">
        <StatCard
          icon={WalletIcon}
          label="Available"
          value={format(data.balances.available)}
          sub="Ready to withdraw"
          tone="green"
          testid="stat-available"
        />
        <StatCard
          icon={Snowflake}
          label="Frozen"
          value={format(data.balances.frozen)}
          sub="Releases on delivery"
          tone="amber"
          testid="stat-frozen"
        />
        <StatCard
          icon={Clock}
          label="Pending withdrawals"
          value={format(data.balances.pending_withdrawals)}
          sub={`${data.pending_withdrawals_list?.length || 0} request${(data.pending_withdrawals_list?.length || 0) === 1 ? "" : "s"} in review`}
          tone="blue"
          testid="stat-pending"
        />
        <StatCard
          icon={TrendingUp}
          label="Lifetime total"
          value={format(data.balances.lifetime_total)}
          sub={`Earned in last ${data.window.days}d: ${format(data.window.total_earned)}`}
          tone="red"
          testid="stat-lifetime"
        />
      </div>

      {/* Chart */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-6" data-testid="payout-chart-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-bold text-neutral-900 dark:text-neutral-100">Earnings over time</h2>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">Frozen inflow vs released funds vs withdrawals</p>
          </div>
        </div>
        <div className="h-72" data-testid="payout-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="frozenGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#F59E0B" stopOpacity={0.6} />
                  <stop offset="100%" stopColor="#F59E0B" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="releasedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10B981" stopOpacity={0.6} />
                  <stop offset="100%" stopColor="#10B981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="wdGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#FF211F" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#FF211F" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-neutral-200 dark:text-neutral-800" />
              <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }} stroke="currentColor" className="text-neutral-400" />
              <YAxis tick={{ fontSize: 11 }} stroke="currentColor" className="text-neutral-400" width={60}
                tickFormatter={(v) => format(v).replace(/\.00$/, "")} />
              <Tooltip
                contentStyle={{ borderRadius: 12, border: "1px solid rgba(0,0,0,0.08)", fontSize: 12 }}
                formatter={(v, name) => [format(v), name]}
                labelFormatter={(l) => `On ${l}`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="frozen_in" name="Frozen in" stroke="#F59E0B" fill="url(#frozenGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="released" name="Released" stroke="#10B981" fill="url(#releasedGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="withdrawal" name="Withdrawn" stroke="#FF211F" fill="url(#wdGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Window totals */}
      <div className="mt-6 grid sm:grid-cols-4 gap-3 sm:gap-4">
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4" data-testid="window-earned">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">Earned ({data.window.days}d)</div>
          <div className="mt-1 text-xl font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(data.window.total_earned)}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">Frozen in ({data.window.days}d)</div>
          <div className="mt-1 text-xl font-extrabold text-amber-600 tabular-nums">{format(data.window.total_frozen_in)}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">Released ({data.window.days}d)</div>
          <div className="mt-1 text-xl font-extrabold text-emerald-600 tabular-nums">{format(data.window.total_released)}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">Withdrawn ({data.window.days}d)</div>
          <div className="mt-1 text-xl font-extrabold text-[#FF211F] tabular-nums">{format(data.window.total_withdrawn)}</div>
        </div>
      </div>

      <div className="mt-6 grid lg:grid-cols-[1fr_360px] gap-6">
        {/* Top listings */}
        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5" data-testid="top-listings-card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-neutral-900 dark:text-neutral-100">Top selling listings</h2>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">Last {data.window.days} days</span>
          </div>
          {data.top_listings.length === 0 ? (
            <div className="text-center py-10 text-sm text-neutral-500 dark:text-neutral-400">
              No sales in this window yet.
            </div>
          ) : (
            <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {data.top_listings.map((l, i) => (
                <li key={l.listing_id} className="flex items-center gap-3 py-2.5" data-testid={`top-listing-${i}`}>
                  <span className="h-6 w-6 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 text-xs font-bold grid place-items-center tabular-nums">{i + 1}</span>
                  {l.image ? (
                    <img src={l.image} alt="" className="h-10 w-10 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800 shrink-0" />
                  ) : (
                    <div className="h-10 w-10 rounded-lg bg-neutral-100 dark:bg-neutral-800 grid place-items-center shrink-0"><PackageIcon className="h-4 w-4 text-neutral-400" /></div>
                  )}
                  <Link to={`/listing/${l.listing_id}`} className="flex-1 min-w-0 text-sm text-neutral-900 dark:text-neutral-100 line-clamp-1 hover:text-[#FF211F]">{l.title}</Link>
                  <span className="text-xs text-neutral-500 dark:text-neutral-400 tabular-nums shrink-0">{l.sales} sale{l.sales === 1 ? "" : "s"}</span>
                  <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 tabular-nums shrink-0 min-w-16 text-right">{format(l.earnings)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Next release + actions */}
        <div className="space-y-4">
          {data.next_release ? (
            <div className="rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-5" data-testid="next-release-card">
              <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200 text-[10px] uppercase tracking-wider font-semibold">
                <CalendarClock className="h-3.5 w-3.5" /> Next expected release
              </div>
              <h3 className="mt-1 font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-2">{data.next_release.listing_title}</h3>
              <div className="mt-2 text-2xl font-extrabold tabular-nums text-amber-700 dark:text-amber-200">{format(data.next_release.seller_earnings || 0)}</div>
              {daysLeft !== null && (
                <div className="mt-1 text-xs text-amber-800 dark:text-amber-200">
                  {daysLeft > 0 ? `Arrives in ~${daysLeft} day${daysLeft === 1 ? "" : "s"} — funds unlock once the buyer confirms.` : "Delivery expected any day now."}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 text-center" data-testid="next-release-empty">
              <Snowflake className="h-6 w-6 mx-auto text-neutral-300 mb-2" />
              <div className="text-sm text-neutral-500 dark:text-neutral-400">No frozen sales — all earnings are available.</div>
            </div>
          )}
          <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
            <h3 className="font-bold text-neutral-900 dark:text-neutral-100">Ready to cash out?</h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">You can withdraw available funds anytime — frozen and pending don&apos;t count.</p>
            <Link to="/wallet">
              <Button className="mt-3 w-full h-10 rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white font-semibold shadow-sm" data-testid="cta-withdraw">
                <ArrowUpRight className="h-4 w-4 mr-1.5" /> Request withdrawal
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PayoutDashboard;
