import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Database, RefreshCw, CheckCircle2, ArrowRight, LayoutGrid, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

/**
 * Compact live "importing X of Y" ticker for the Admin dashboard.
 * Polls /admin/sync/status every 3s while a sync is running, every 30s while idle.
 * Shows a progress bar, imported/target, running time, and a link to full sync page.
 */
const formatDuration = (s) => {
  if (s == null) return "";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return sec ? `${m}m ${sec}s` : `${m}m`;
};

const ApifySyncTicker = () => {
  const [status, setStatus] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [rebalancing, setRebalancing] = useState(false);
  const [rebalanceResult, setRebalanceResult] = useState(null);
  const { toast } = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/sync/status");
      setStatus(data);
    } catch {
      // Silent — dashboard should degrade gracefully
    }
  }, []);

  const rebalance = useCallback(async () => {
    if (rebalancing) return;
    if (!window.confirm("Reclassify every listing with the smart keyword classifier and top-up empty categories to at least 20 items each?\n\nThis takes ~30s and clears any stuck sync flag.")) return;
    setRebalancing(true);
    setRebalanceResult(null);
    try {
      const { data } = await api.post("/admin/listings/rebalance", { min_per_category: 20, clear_sync_flag: true });
      setRebalanceResult(data);
      toast({
        title: "Rebalance complete",
        description: `Reclassified ${data.reclassified} listings · filled ${data.duplicates_created} category slots`,
      });
      await load();
    } catch (e) {
      toast({
        title: "Rebalance failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setRebalancing(false);
    }
  }, [rebalancing, load, toast]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const interval = status?.sync_running ? 3000 : 30000;
    const iv = setInterval(load, interval);
    return () => clearInterval(iv);
  }, [status?.sync_running, load]);

  // Local ticking clock so "running for" updates smoothly even between polls
  useEffect(() => {
    if (!status?.sync_running) return;
    const iv = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(iv);
  }, [status?.sync_running]);

  if (!status) return null;

  const running = !!status.sync_running;
  const imported = status.imported_count || 0;
  const target = status.target_count || 0;
  const raw = status.raw_items || 0;
  const pct = target > 0 ? Math.min(100, Math.round((imported / target) * 100)) : 0;
  const startedAt = status.started_at ? new Date(status.started_at).getTime() : null;
  const runningFor = running && startedAt ? Math.max(0, Math.round((now - startedAt) / 1000)) : null;

  return (
    <div
      className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl p-5 shadow-sm"
      data-testid="admin-apify-sync-ticker"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div
            className={`h-10 w-10 rounded-xl grid place-items-center ${
              running
                ? "bg-amber-100 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300"
                : "bg-emerald-100 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300"
            }`}
          >
            {running ? (
              <RefreshCw className="h-5 w-5 animate-spin" />
            ) : (
              <CheckCircle2 className="h-5 w-5" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-neutral-900 dark:text-neutral-100">
                Apify sync
              </span>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                  running
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                    : "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                }`}
                data-testid="apify-ticker-state"
              >
                {running ? "Running" : "Idle"}
              </span>
            </div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              {running
                ? status.message || "Contacting Apify actor…"
                : status.last_sync_at
                ? `Last full sync: ${new Date(status.last_sync_at).toLocaleString()}`
                : "No sync has run yet"}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={rebalance}
            disabled={rebalancing}
            className="inline-flex items-center gap-1.5 text-sm text-neutral-700 dark:text-neutral-300 border border-neutral-200 dark:border-neutral-700 rounded-full px-3 py-1 hover:border-[#FF211F] hover:text-[#FF211F] transition-colors disabled:opacity-60"
            data-testid="apify-ticker-rebalance-btn"
          >
            {rebalancing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LayoutGrid className="h-3.5 w-3.5" />}
            <span className="text-xs font-semibold">Rebalance categories</span>
          </button>
          <Link
            to="/admin/apify-sync"
            className="inline-flex items-center gap-1 text-sm text-[#FF211F] hover:underline"
            data-testid="apify-ticker-open-link"
          >
            Open <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>

      {rebalanceResult && (
        <div className="mt-4 rounded-lg border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/40 p-3 text-xs" data-testid="apify-ticker-rebalance-result">
          <div className="font-semibold text-emerald-800 dark:text-emerald-200 mb-1">
            Rebalance complete — {rebalanceResult.reclassified} reclassified, {rebalanceResult.listings_tagged ?? rebalanceResult.duplicates_created ?? 0} listings cross-tagged to fill sparse categories.
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {Object.entries(rebalanceResult.counts_after || {}).map(([slug, count]) => (
              <span
                key={slug}
                className="inline-flex items-center gap-1 rounded-full bg-white dark:bg-neutral-900 border border-emerald-200 dark:border-emerald-900 px-2 py-0.5 text-[11px] font-medium text-neutral-700 dark:text-neutral-200"
              >
                {slug} <span className="text-emerald-700 dark:text-emerald-300 tabular-nums">· {count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {running ? (
        <>
          <div className="mt-4 flex items-end justify-between">
            <div>
              <div className="text-2xl font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">
                <span data-testid="apify-ticker-imported">{imported.toLocaleString()}</span>
                <span className="text-neutral-400 dark:text-neutral-500 text-lg font-medium">
                  {" "}
                  / {target.toLocaleString()}
                </span>
              </div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                products imported · {raw.toLocaleString()} raw items scraped
              </div>
            </div>
            <div className="text-right">
              <div className="text-lg font-semibold tabular-nums text-neutral-800 dark:text-neutral-200">
                {pct}%
              </div>
              {runningFor !== null && (
                <div className="text-xs text-neutral-500 dark:text-neutral-400">
                  {formatDuration(runningFor)} elapsed
                </div>
              )}
            </div>
          </div>

          <div
            className="mt-3 h-2.5 w-full rounded-full bg-neutral-100 dark:bg-neutral-800 overflow-hidden"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            data-testid="apify-ticker-progress"
          >
            <div
              className="h-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] transition-all duration-500 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>

          <div className="mt-3 text-[11px] text-neutral-500 dark:text-neutral-400 flex items-center gap-1.5">
            <Database className="h-3 w-3" /> Auto-refreshing every 3s while running
          </div>
        </>
      ) : (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="rounded-lg bg-neutral-50 dark:bg-neutral-800/60 px-3 py-2">
            <div className="text-[11px] text-neutral-500 dark:text-neutral-400">Active</div>
            <div className="text-lg font-semibold tabular-nums">
              {(status.active_listings || 0).toLocaleString()}
            </div>
          </div>
          <div className="rounded-lg bg-neutral-50 dark:bg-neutral-800/60 px-3 py-2">
            <div className="text-[11px] text-neutral-500 dark:text-neutral-400">Imported</div>
            <div className="text-lg font-semibold tabular-nums">
              {imported.toLocaleString()}
            </div>
          </div>
          <div className="rounded-lg bg-neutral-50 dark:bg-neutral-800/60 px-3 py-2">
            <div className="text-[11px] text-neutral-500 dark:text-neutral-400">Raw scraped</div>
            <div className="text-lg font-semibold tabular-nums">{raw.toLocaleString()}</div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApifySyncTicker;
