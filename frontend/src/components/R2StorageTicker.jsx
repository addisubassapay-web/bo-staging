import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { HardDrive, CloudUpload, CheckCircle2, Loader2, AlertTriangle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

/**
 * R2StorageTicker — live "images on our CDN" progress card for the
 * Admin dashboard. Polls /admin/products/r2-rehost/status every 5s and
 * offers a one-click "Rehost next 25" button that streams the next
 * batch through the backend batch endpoint.
 */
const R2StorageTicker = () => {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const { toast } = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/products/r2-rehost/status");
      setState(data);
    } catch (e) {
      // Silent — component degrades gracefully.
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const rehostBatch = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/products/r2-rehost", { limit: 25 });
      setLastResult(data);
      toast({
        title: "Rehost batch complete",
        description: `${data.processed} products · ${data.rehosted_images} images · ${data.remaining} remaining`,
      });
      load();
    } catch (e) {
      toast({
        title: "Rehost failed",
        description: e?.response?.data?.detail || "Unable to run the batch",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  if (!state) {
    return (
      <div
        data-testid="r2-ticker-loading"
        className="rounded-xl border border-neutral-200 bg-white p-4 flex items-center gap-3 text-sm text-neutral-500"
      >
        <Loader2 className="w-4 h-4 animate-spin" /> Loading R2 storage status…
      </div>
    );
  }

  const s = state.storage || {};
  const provider = s.provider || "unknown";
  const pct = state.pct_complete ?? 0;
  const enabled = !!s.enabled && provider === "cloudflare_r2";

  return (
    <div
      data-testid="r2-storage-ticker"
      className="rounded-xl border border-neutral-200 bg-white p-4 sm:p-5 space-y-3"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          {enabled ? (
            <CloudUpload className="w-5 h-5 text-emerald-600" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          )}
          <div>
            <div className="font-semibold text-sm text-neutral-900">
              {enabled ? "Cloudflare R2" : "Local disk"}
              <span className="ml-2 inline-flex items-center gap-1 text-[11px] font-medium text-neutral-500">
                <HardDrive className="w-3 h-3" />
                {enabled ? s.bucket : "no CDN configured"}
              </span>
            </div>
            <div className="text-xs text-neutral-500 truncate max-w-md">
              {s.public_base}
            </div>
          </div>
        </div>
        <button
          onClick={rehostBatch}
          disabled={busy || state.remaining === 0 || !enabled}
          data-testid="r2-rehost-batch-btn"
          className="text-sm font-medium px-3 h-9 rounded-full bg-[#DC2626] text-white hover:bg-[#e01a19] transition-colors disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-2"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CloudUpload className="w-4 h-4" />}
          {state.remaining === 0 ? "All rehosted" : "Rehost next 25"}
        </button>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-neutral-600">
          <span>
            {state.rehosted} / {state.total_active} products on R2
          </span>
          <span className="font-medium">{pct}%</span>
        </div>
        <div
          className="h-2 rounded-full bg-neutral-100 overflow-hidden"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <div
            className="h-full bg-emerald-500 transition-all duration-500"
            style={{ width: `${Math.min(100, pct)}%` }}
            data-testid="r2-progress-fill"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-[11px]">
        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 font-medium">
          <CheckCircle2 className="w-3 h-3" /> {state.rehosted} rehosted
        </span>
        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-neutral-100 text-neutral-700 font-medium">
          {state.remaining} remaining
        </span>
        {state.failed > 0 && (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-red-50 text-red-700 font-medium">
            <AlertTriangle className="w-3 h-3" /> {state.failed} failed
          </span>
        )}
        {lastResult && (
          <span
            className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-blue-50 text-blue-700 font-medium"
            data-testid="r2-last-result"
          >
            Last run: +{lastResult.rehosted_images} images
          </span>
        )}
      </div>

      {!enabled && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
          R2 credentials are not configured. Add <code>R2_ACCOUNT_ID</code>,{" "}
          <code>R2_ACCESS_KEY_ID</code>, <code>R2_SECRET_ACCESS_KEY</code>, and{" "}
          <code>R2_BUCKET</code> in <code>backend/.env</code> to enable rehosting.
        </div>
      )}
    </div>
  );
};

export default R2StorageTicker;
