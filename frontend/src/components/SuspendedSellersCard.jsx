import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { ShieldAlert, ShieldCheck, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";

/**
 * SuspendedSellersCard — admin dashboard card that lists sellers whose
 * listings were auto-suspended by the health-sweep loop (poor tier for
 * 7 consecutive days). Each row has a 1-click "Unlock" button that hits
 * /admin/users/{id}/unlock-listings.
 */
const SuspendedSellersCard = () => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState({});
  const { toast } = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/users/suspended-listings");
      setData(data);
    } catch (e) {
      /* silent */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const unlock = async (userId) => {
    if (busy[userId]) return;
    setBusy((b) => ({ ...b, [userId]: true }));
    try {
      const { data } = await api.post(`/admin/users/${userId}/unlock-listings`);
      toast({
        title: "Listings restored",
        description: `${data.listings_restored} listing${data.listings_restored === 1 ? "" : "s"} back online`,
      });
      load();
    } catch (e) {
      toast({
        title: "Unlock failed",
        description: e?.response?.data?.detail || "Try again in a moment",
        variant: "destructive",
      });
    } finally {
      setBusy((b) => ({ ...b, [userId]: false }));
    }
  };

  if (!data) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-4 flex items-center gap-2 text-sm text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading suspended sellers…
      </div>
    );
  }

  if (data.count === 0) {
    return (
      <div
        data-testid="suspended-sellers-card"
        className="rounded-xl border border-neutral-200 bg-white p-4 flex items-center gap-3 text-sm text-emerald-700"
      >
        <ShieldCheck className="w-5 h-5" />
        <div>
          <div className="font-semibold text-neutral-900">No sellers suspended for poor health</div>
          <div className="text-xs text-neutral-500">Auto-pause triggers after 7 straight days at &lsquo;poor&rsquo; tier.</div>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="suspended-sellers-card"
      className="rounded-xl border border-red-200 bg-white overflow-hidden"
    >
      <div className="px-4 py-3 bg-red-50 border-b border-red-200 flex items-center gap-2">
        <ShieldAlert className="w-5 h-5 text-red-700" />
        <div>
          <div className="font-semibold text-red-900">
            {data.count} seller{data.count === 1 ? "" : "s"} auto-suspended for poor store health
          </div>
          <div className="text-xs text-red-700">Review and unlock once the seller has improved their acceptance rate.</div>
        </div>
      </div>
      <div className="divide-y divide-neutral-200">
        {data.users.map((u) => (
          <div key={u.id} className="px-4 py-3 flex items-center gap-3 flex-wrap" data-testid={`suspended-row-${u.id}`}>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-neutral-900 truncate">
                {u.username || u.email}
              </div>
              <div className="text-xs text-neutral-600 flex flex-wrap items-center gap-3 mt-0.5">
                <span>{u.email}</span>
                <span>Score: <span className="font-mono text-red-700 font-semibold">{u.health_score ?? "—"}</span></span>
                <span>Poor for: <span className="font-mono">{u.health_poor_streak_days ?? "?"}d</span></span>
                <span>{u.suspended_listing_count} listing{u.suspended_listing_count === 1 ? "" : "s"} paused</span>
              </div>
            </div>
            <Button
              size="sm"
              onClick={() => unlock(u.id)}
              disabled={busy[u.id]}
              data-testid={`unlock-listings-btn-${u.id}`}
              className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-full"
            >
              {busy[u.id] ? (
                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Unlocking</>
              ) : (
                <><RotateCcw className="w-4 h-4 mr-1.5" /> Unlock listings</>
              )}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SuspendedSellersCard;
