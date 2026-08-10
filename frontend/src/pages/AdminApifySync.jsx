import React, { useEffect, useMemo, useState } from "react";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import {
  Database, RefreshCw, Zap, CheckCircle2, Package, Clock,
  Shirt, User, Baby, Smartphone, Home as HomeIcon, Sparkles, Dumbbell,
  Gamepad2, Book, Palette, Boxes, TrendingUp,
} from "lucide-react";

// Warm palette per category (Tailwind text + bar bg)
const CATEGORY_META = {
  women:       { label: "Women",       Icon: Shirt,      bar: "from-rose-400 to-rose-500",         text: "text-rose-600 dark:text-rose-300" },
  men:         { label: "Men",         Icon: User,       bar: "from-sky-400 to-sky-500",           text: "text-sky-600 dark:text-sky-300" },
  kids:        { label: "Kids",        Icon: Baby,       bar: "from-amber-400 to-amber-500",       text: "text-amber-600 dark:text-amber-300" },
  electronics: { label: "Electronics", Icon: Smartphone, bar: "from-indigo-400 to-indigo-500",     text: "text-indigo-600 dark:text-indigo-300" },
  home:        { label: "Home",        Icon: HomeIcon,   bar: "from-emerald-400 to-emerald-500",   text: "text-emerald-600 dark:text-emerald-300" },
  beauty:      { label: "Beauty",      Icon: Sparkles,   bar: "from-pink-400 to-pink-500",         text: "text-pink-600 dark:text-pink-300" },
  sports:      { label: "Sports",      Icon: Dumbbell,   bar: "from-orange-400 to-orange-500",     text: "text-orange-600 dark:text-orange-300" },
  toys:        { label: "Toys",        Icon: Gamepad2,   bar: "from-fuchsia-400 to-fuchsia-500",   text: "text-fuchsia-600 dark:text-fuchsia-300" },
  books:       { label: "Books",       Icon: Book,       bar: "from-teal-400 to-teal-500",         text: "text-teal-600 dark:text-teal-300" },
  handmade:    { label: "Handmade",    Icon: Palette,    bar: "from-yellow-400 to-yellow-500",     text: "text-yellow-600 dark:text-yellow-300" },
  other:       { label: "Other",       Icon: Boxes,      bar: "from-neutral-400 to-neutral-500",   text: "text-neutral-600 dark:text-neutral-300" },
};

const CategoryBreakdownCard = ({ perCategory, running }) => {
  const rows = useMemo(() => {
    const entries = Object.entries(perCategory || {}).filter(([, v]) => v > 0);
    return entries.sort((a, b) => b[1] - a[1]);
  }, [perCategory]);
  const total = useMemo(() => rows.reduce((s, [, v]) => s + v, 0), [rows]);
  const max = rows[0]?.[1] || 1;

  if (rows.length === 0) {
    return (
      <div
        className="mt-6 bg-white dark:bg-neutral-900 border border-dashed border-neutral-300 dark:border-neutral-700 rounded-2xl p-8 text-center"
        data-testid="apify-category-breakdown-empty"
      >
        <TrendingUp className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mx-auto" />
        <div className="mt-2 font-semibold text-neutral-700 dark:text-neutral-200">
          {running ? "Classifying items…" : "No category data yet"}
        </div>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          {running
            ? "This card will populate as the scrape processes each item — refresh every 5 seconds."
            : "Trigger a sync above to see per-department import breakdowns here."}
        </p>
      </div>
    );
  }

  return (
    <div
      className="mt-6 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl p-5 sm:p-6"
      data-testid="apify-category-breakdown"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
        <div>
          <h3 className="font-bold text-lg flex items-center gap-2">
            <Package className="h-5 w-5 text-[#FF7A18]" /> Distribution by department
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            {running
              ? "Live counts — this run is still processing."
              : `Snapshot of the last completed run — ${rows.length} departments filled.`}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums" data-testid="apify-breakdown-total">
            {total.toLocaleString()}
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">Total imported</div>
        </div>
      </div>

      <ul className="space-y-2.5">
        {rows.map(([slug, count]) => {
          const meta = CATEGORY_META[slug] || CATEGORY_META.other;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const barPct = max > 0 ? (count / max) * 100 : 0;
          const Icon = meta.Icon;
          return (
            <li
              key={slug}
              className="group"
              data-testid={`apify-breakdown-row-${slug}`}
            >
              <div className="flex items-center justify-between text-sm mb-1.5">
                <div className={`flex items-center gap-2 font-medium ${meta.text}`}>
                  <Icon className="h-4 w-4" />
                  <span className="text-neutral-800 dark:text-neutral-100">{meta.label}</span>
                </div>
                <div className="flex items-center gap-3 tabular-nums">
                  <span className="text-neutral-500 dark:text-neutral-400 text-xs">{pct.toFixed(1)}%</span>
                  <span className="font-semibold text-neutral-900 dark:text-neutral-100">{count.toLocaleString()}</span>
                </div>
              </div>
              <div className="h-2 rounded-full bg-neutral-100 dark:bg-neutral-800 overflow-hidden">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${meta.bar} transition-all duration-700 ease-out`}
                  style={{ width: `${Math.max(3, barPct)}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>

      {running && (
        <div className="mt-4 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg px-3 py-2 flex items-center gap-2">
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          Counts update every ~200 items processed. Refresh cadence: 5s.
        </div>
      )}
    </div>
  );
};

const ApifySync = () => {
  const { toast } = useToast();
  const [status, setStatus] = useState(null);
  const [target, setTarget] = useState(5000);
  const [replace, setReplace] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const load = () => api.get("/admin/sync/status").then((r) => setStatus(r.data));

  useEffect(() => {
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, []);

  const runSync = async () => {
    if (!window.confirm(`Scrape ${target.toLocaleString()} Amazon products via Apify?\n${replace ? "This will REPLACE all existing listings." : "Existing listings will be preserved."}\n\nThis may take 5-15 minutes and use Apify credits (~$${(target * 0.0012).toFixed(2)}).`)) return;
    setSyncing(true);
    try {
      const { data } = await api.post("/admin/sync/apify", { target_count: Number(target), replace_existing: replace });
      if (data.already_running) {
        toast({ title: "Sync already running", description: "Watch the progress card." });
      } else {
        toast({ title: "Sync started", description: "Running in background. Watch progress here (updates every 5s)." });
      }
      load();
    } catch (err) {
      toast({ title: "Sync failed", description: err.response?.data?.detail || err.response?.data?.error || "Try again", variant: "destructive" });
    } finally {
      setSyncing(false);
    }
  };

  if (!status) return <div>Loading…</div>;

  const startedAt = status.started_at ? new Date(status.started_at) : null;
  const runningFor = startedAt && status.sync_running
    ? Math.round((Date.now() - startedAt.getTime()) / 1000)
    : null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Database className="h-6 w-6 text-[#FF211F]" />
        <h2 className="text-2xl font-bold">Apify Amazon Sync</h2>
      </div>
      <p className="text-neutral-600 mb-6">
        Live product data scraped from Amazon.com via <span className="font-mono text-xs bg-neutral-100 px-1.5 py-0.5 rounded">junglee/amazon-crawler</span>.
        Auto-syncs weekly; you can also trigger a manual sync below.
      </p>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white border border-neutral-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <RefreshCw className="h-4 w-4 text-neutral-500" />
            <h3 className="font-semibold">Manual sync</h3>
          </div>
          <div className="space-y-3">
            <div>
              <Label>Target listings</Label>
              <Input type="number" min="100" max="20000" step="500" value={target} onChange={(e) => setTarget(e.target.value)} className="mt-1" />
              <div className="text-xs text-neutral-500 mt-1">100 to 20,000 · Est. cost ${(target * 0.0012).toFixed(2)}</div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="h-4 w-4" />
              Replace all existing listings (recommended)
            </label>
            <Button onClick={runSync} disabled={syncing || status.sync_running} className="w-full bg-[#FF211F] hover:bg-[#e01d1b]">
              <RefreshCw className={`h-4 w-4 mr-1 ${status.sync_running ? "animate-spin" : ""}`} />
              {status.sync_running ? "Sync running…" : "Sync now"}
            </Button>
            {status.sync_running && (
              <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-900">
                <div className="flex items-center gap-2 font-medium mb-1">
                  <Clock className="h-4 w-4" /> Scrape in progress
                </div>
                <div className="text-xs">{status.message || "Contacting Apify actor…"}</div>
                {runningFor !== null && (
                  <div className="text-xs mt-1 text-amber-800">
                    Running for {runningFor < 60 ? `${runningFor}s` : `${Math.round(runningFor / 60)}m`}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white border border-neutral-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="h-4 w-4 text-green-500" />
            <h3 className="font-semibold">Live sync status</h3>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-neutral-500">Source</span><span className="font-mono text-xs">{status.source}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Active listings</span><span className="font-semibold">{status.active_listings?.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Sold listings</span><span>{status.sold_listings?.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Imported total</span><span>{status.imported_count?.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Raw items from Apify</span><span>{status.raw_items?.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Last full sync</span><span className="text-xs">{status.last_sync_at ? new Date(status.last_sync_at).toLocaleString() : "Never"}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Last live tick</span><span className="text-xs">{status.last_live_tick ? new Date(status.last_live_tick).toLocaleString() : "—"}</span></div>
            <div className="flex justify-between items-center pt-2 border-t">
              <span className="text-neutral-500">Live simulator</span>
              <span className="flex items-center gap-1 text-green-600 text-xs font-medium">
                <CheckCircle2 className="h-3 w-3" /> Running every 60s
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-neutral-500">Auto-sync</span>
              <span className="flex items-center gap-1 text-green-600 text-xs font-medium">
                <CheckCircle2 className="h-3 w-3" /> Every 7 days
              </span>
            </div>
          </div>
        </div>
      </div>

      <CategoryBreakdownCard perCategory={status.per_category} running={status.sync_running} />

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-900">
        <strong>How it works:</strong> The <em>junglee/amazon-crawler</em> Apify actor scrapes Amazon.com bestseller pages across 11 department categories (Women, Men, Kids, Electronics, Home, Beauty, Sports, Toys, Books, Handmade, Other). Product data — including real photos, prices, ratings, and descriptions — is imported into MongoDB. A live-simulation loop rotates featured items every 60 seconds; a full re-scrape runs automatically once a week.
      </div>
    </div>
  );
};

export default ApifySync;
