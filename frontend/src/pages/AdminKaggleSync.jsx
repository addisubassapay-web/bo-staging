import React, { useEffect, useState } from "react";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Database, RefreshCw, Zap, CheckCircle2 } from "lucide-react";

const KaggleSync = () => {
  const { toast } = useToast();
  const [status, setStatus] = useState(null);
  const [target, setTarget] = useState(10000);
  const [replace, setReplace] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const load = () => api.get("/admin/sync/status").then((r) => setStatus(r.data));

  useEffect(() => {
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, []);

  const runSync = async () => {
    if (!window.confirm(`Import ${target.toLocaleString()} listings from Kaggle?\n${replace ? "This will REPLACE all existing listings." : "Existing listings will be preserved."}`)) return;
    setSyncing(true);
    try {
      const { data } = await api.post("/admin/sync/kaggle", { target_count: Number(target), replace_existing: replace });
      toast({ title: "Sync complete", description: `Imported ${data.imported} listings from ${data.processed} scanned rows.` });
      load();
    } catch (err) {
      toast({ title: "Sync failed", description: err.response?.data?.detail || err.response?.data?.error || "Try again", variant: "destructive" });
    } finally {
      setSyncing(false);
    }
  };

  if (!status) return <div>Loading…</div>;

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Database className="h-6 w-6 text-[#FF211F]" />
        <h2 className="text-2xl font-bold">Kaggle Data Sync</h2>
      </div>
      <p className="text-neutral-600 mb-6">Import real Mercari Japan product listings from Kaggle. Prices are automatically converted to USD.</p>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white border border-neutral-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <RefreshCw className="h-4 w-4 text-neutral-500" />
            <h3 className="font-semibold">Manual sync</h3>
          </div>
          <div className="space-y-3">
            <div>
              <Label>Target listings</Label>
              <Input type="number" min="100" max="100000" step="1000" value={target} onChange={(e) => setTarget(e.target.value)} className="mt-1" />
              <div className="text-xs text-neutral-500 mt-1">100 to 100,000</div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="h-4 w-4" />
              Replace all existing listings (recommended)
            </label>
            <Button onClick={runSync} disabled={syncing} className="w-full bg-[#FF211F] hover:bg-[#e01d1b]">
              <RefreshCw className={`h-4 w-4 mr-1 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? "Syncing… (may take up to a minute)" : "Sync now"}
            </Button>
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
            <div className="flex justify-between"><span className="text-neutral-500">Rows scanned</span><span>{status.processed_rows?.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Last full sync</span><span className="text-xs">{status.last_sync_at ? new Date(status.last_sync_at).toLocaleString() : "Never"}</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Last live tick</span><span className="text-xs">{status.last_live_tick ? new Date(status.last_live_tick).toLocaleString() : "—"}</span></div>
            <div className="flex justify-between items-center pt-2 border-t">
              <span className="text-neutral-500">Live simulator</span>
              <span className="flex items-center gap-1 text-green-600 text-xs font-medium">
                <CheckCircle2 className="h-3 w-3" /> Running every 60s
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-900">
        <strong>About live sync:</strong> Every 60 seconds the platform simulates real-time market activity — rotating featured items, updating view/like counts on random listings, and marking a few items as sold. The status indicator in the header reflects this activity.
      </div>
    </div>
  );
};

export default KaggleSync;
