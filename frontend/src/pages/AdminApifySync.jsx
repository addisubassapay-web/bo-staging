import React, { useEffect, useState } from "react";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Database, RefreshCw, Zap, CheckCircle2, Package, Clock } from "lucide-react";

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
        Auto-syncs every 24 hours; you can also trigger a manual sync below.
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
                <CheckCircle2 className="h-3 w-3" /> Every 24 hours
              </span>
            </div>
          </div>
        </div>
      </div>

      {Object.keys(status.per_category || {}).length > 0 && (
        <div className="mt-6 bg-white border border-neutral-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <Package className="h-4 w-4 text-neutral-500" />
            <h3 className="font-semibold">Distribution by category</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(status.per_category).map(([k, v]) => (
              <div key={k} className="bg-neutral-50 rounded p-3">
                <div className="text-xs text-neutral-500 capitalize">{k}</div>
                <div className="font-semibold">{v.toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-900">
        <strong>How it works:</strong> The <em>junglee/amazon-crawler</em> Apify actor scrapes Amazon.com bestseller pages across 11 department categories (Women, Men, Kids, Electronics, Home, Beauty, Sports, Toys, Books, Handmade, Other). Product data — including real photos, prices, ratings, and descriptions — is imported into MongoDB. A live-simulation loop rotates featured items every 60 seconds; a full re-scrape runs automatically every 24 hours.
      </div>
    </div>
  );
};

export default ApifySync;
