import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { RefreshCw, TrendingDown, Loader2, ArrowUpCircle, Trash2, AlertTriangle } from "lucide-react";

const BestSellersRotation = () => {
  const { toast } = useToast();
  const [status, setStatus] = useState(null);
  const [demoted, setDemoted] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [prices, setPrices] = useState({}); // listing_id -> new price draft
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([
        api.get("/scraper/best-sellers/status"),
        api.get("/scraper/demoted"),
      ]);
      setStatus(s.data);
      setDemoted(d.data.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const refreshNow = async () => {
    setRefreshing(true);
    try {
      const { data } = await api.post("/scraper/best-sellers/refresh", null, { params: { limit: 20 } });
      toast({
        title: "Rotation complete",
        description: `${data.checked} checked · ${data.demoted_price} price-shift · ${data.demoted_gone} gone`,
      });
      await load();
    } catch (e) {
      toast({
        title: "Refresh failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setRefreshing(false); }
  };

  const restore = async (row, useNewPrice = false) => {
    setBusy(row.id + ":restore");
    try {
      const body = useNewPrice && (prices[row.id] || row.supplier_last_price)
        ? { new_price: Number(prices[row.id] || row.supplier_last_price) }
        : {};
      await api.post(`/scraper/demoted/${row.id}/restore`, body);
      toast({ title: "Listing restored" });
      await load();
    } catch (e) {
      toast({ title: "Restore failed", variant: "destructive" });
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6" data-testid="best-sellers-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-rose-500 to-orange-500 text-white grid place-items-center shrink-0">
            <TrendingDown className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold">Best sellers rotation</h3>
            <p className="text-sm text-neutral-600 mt-1">
              Every Monday at 08:00 UTC we re-check your top-100 imported listings. Anything whose supplier price moved &gt;15% (or vanished) is demoted so your storefront stays fresh. You can restore any listing with one click after reviewing the new price.
            </p>
          </div>
        </div>
        <Button
          onClick={refreshNow}
          disabled={refreshing}
          className="bg-[#FF211F] hover:bg-[#e01d1b]"
          data-testid="best-sellers-refresh"
        >
          {refreshing ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Rotating…</> : <><RefreshCw className="h-4 w-4 mr-1.5" /> Rotate now (top 20)</>}
        </Button>
      </div>

      {status && (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm" data-testid="best-sellers-stats">
          <div className="rounded-lg bg-neutral-50 p-3">
            <div className="text-xs text-neutral-500">Eligible imports</div>
            <div className="font-bold tabular-nums text-lg">{status.your_eligible}</div>
          </div>
          <div className="rounded-lg bg-rose-50 p-3">
            <div className="text-xs text-rose-600">Currently demoted</div>
            <div className="font-bold tabular-nums text-lg text-rose-700">{status.your_demoted}</div>
          </div>
          <div className="rounded-lg bg-neutral-50 p-3">
            <div className="text-xs text-neutral-500">Drift threshold</div>
            <div className="font-bold tabular-nums text-lg">±{status.drift_threshold_pct}%</div>
          </div>
          <div className="rounded-lg bg-neutral-50 p-3">
            <div className="text-xs text-neutral-500">Last cron run</div>
            <div className="font-medium text-xs mt-1">
              {status.last_run?.finished_at ? new Date(status.last_run.finished_at).toLocaleString() : "Not run yet"}
            </div>
          </div>
        </div>
      )}

      {demoted.length > 0 && (
        <div className="mt-5">
          <div className="text-sm font-semibold flex items-center gap-2 mb-2 justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-rose-500" /> Demoted listings ({demoted.length})
            </div>
            <Button
              variant="outline" size="sm"
              onClick={async () => {
                if (!window.confirm(`Restore all ${demoted.length} demoted listings at the new supplier prices?`)) return;
                setBusy("bulk-restore");
                try {
                  const { data } = await api.post("/scraper/demoted/bulk-restore");
                  toast({
                    title: "Bulk restore complete",
                    description: `${data.restored} restored · ${data.repriced} repriced · ${data.skipped_gone} skipped (supplier gone)`,
                  });
                  await load();
                } catch (e) {
                  toast({ title: "Bulk restore failed", variant: "destructive" });
                } finally { setBusy(null); }
              }}
              disabled={busy === "bulk-restore"}
              data-testid="bulk-restore-btn"
            >
              {busy === "bulk-restore"
                ? <><Loader2 className="h-3 w-3 mr-1.5 animate-spin" /> Restoring…</>
                : <><ArrowUpCircle className="h-3 w-3 mr-1.5" /> Restore all at new prices</>}
            </Button>
          </div>
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {demoted.map((row) => {
              const delta = row.supplier_last_price && row.price
                ? (((row.supplier_last_price - row.price) / row.price) * 100).toFixed(1)
                : null;
              const gone = row.demoted_reason === "supplier_gone";
              return (
                <div key={row.id} className="flex items-center gap-3 p-3 rounded-lg border border-rose-100 bg-rose-50/30" data-testid={`demoted-row-${row.id.slice(0,8)}`}>
                  <div className="h-12 w-12 rounded bg-neutral-100 overflow-hidden shrink-0">
                    {row.images?.[0] && <img src={row.images[0]} alt="" className="h-full w-full object-cover" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{row.title}</div>
                    <div className="text-xs text-neutral-500 flex items-center gap-2 flex-wrap">
                      <Badge variant="secondary" className="text-[10px]">{row.category_name}</Badge>
                      <span className="tabular-nums">was ${Number(row.price).toFixed(2)}</span>
                      {row.supplier_last_price != null && (
                        <>
                          <span>→</span>
                          <span className="font-semibold tabular-nums text-neutral-800">${Number(row.supplier_last_price).toFixed(2)}</span>
                          <Badge className={`text-[10px] ${Math.abs(Number(delta)) >= 15 ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"} border-none`}>
                            {Number(delta) > 0 ? "+" : ""}{delta}%
                          </Badge>
                        </>
                      )}
                      {gone && <Badge className="bg-neutral-800 text-white border-none text-[10px]">supplier gone</Badge>}
                    </div>
                  </div>
                  {!gone && (
                    <div className="flex items-center gap-1">
                      <Input
                        type="number" step="0.01"
                        placeholder={String(row.supplier_last_price || row.price)}
                        value={prices[row.id] ?? ""}
                        onChange={(e) => setPrices({ ...prices, [row.id]: e.target.value })}
                        className="w-24 h-8 tabular-nums text-xs"
                        data-testid={`demoted-price-${row.id.slice(0,8)}`}
                      />
                      <Button
                        variant="outline" size="sm"
                        disabled={busy === row.id + ":restore"}
                        onClick={() => restore(row, true)}
                        data-testid={`demoted-restore-${row.id.slice(0,8)}`}
                      >
                        {busy === row.id + ":restore"
                          ? <Loader2 className="h-3 w-3 animate-spin" />
                          : <><ArrowUpCircle className="h-3 w-3 mr-1" /> Restore</>}
                      </Button>
                    </div>
                  )}
                  {gone && (
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => restore(row, false)}
                      disabled={busy === row.id + ":restore"}
                      data-testid={`demoted-restore-${row.id.slice(0,8)}`}
                      title="Restore anyway"
                    >
                      <Trash2 className="h-3 w-3 text-neutral-500" />
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {status && demoted.length === 0 && !loading && (
        <div className="mt-4 text-sm text-neutral-500 py-6 text-center border border-dashed border-neutral-200 rounded-lg">
          No demoted listings. Your storefront is fresh.
        </div>
      )}
    </div>
  );
};

export default BestSellersRotation;
