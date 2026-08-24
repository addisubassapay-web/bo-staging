import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { AlertOctagon, Loader2, Send, Timer, PackageX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/context/AuthContext";

const fmt = (n) => `$${Number(n ?? 0).toFixed(2)}`;

/**
 * StoreAdminNudgeBanner — visible only to admins viewing a store page.
 * Shows any orders on this seller that are stuck in `pending_pickup` and
 * lets admins fire a 1-click nudge (email + in-app notification) to
 * urge the seller to accept.
 */
const StoreAdminNudgeBanner = ({ slug }) => {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState({});
  const { toast } = useToast();

  const load = useCallback(async () => {
    if (!slug || user?.role !== "admin") return;
    try {
      const { data } = await api.get(`/stores/${slug}/pending-pickups`);
      setData(data);
    } catch (e) {
      // 403/404 → non-admin or store not found — silent.
    }
  }, [slug, user]);

  useEffect(() => {
    load();
  }, [load]);

  const nudge = async (orderId) => {
    if (busy[orderId]) return;
    setBusy((b) => ({ ...b, [orderId]: true }));
    try {
      await api.post(`/admin/orders/${orderId}/nudge`);
      toast({ title: "Nudge sent", description: "Seller got an email + in-app alert." });
      load();
    } catch (e) {
      toast({
        title: "Nudge failed",
        description: e?.response?.data?.detail || "Try again in a moment",
        variant: "destructive",
      });
    } finally {
      setBusy((b) => ({ ...b, [orderId]: false }));
    }
  };

  if (user?.role !== "admin" || !data || data.count === 0) return null;

  return (
    <div
      data-testid="admin-nudge-banner"
      className="max-w-6xl mx-auto px-4 pt-4"
    >
      <div className="rounded-xl border-2 border-red-300 bg-red-50 shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center gap-3 border-b border-red-200 bg-red-100/60">
          <AlertOctagon className="w-5 h-5 text-red-700 flex-shrink-0" />
          <div className="flex-1">
            <div className="font-bold text-red-900">
              {data.count} order{data.count === 1 ? "" : "s"} awaiting pickup — nudge seller
            </div>
            <div className="text-xs text-red-700">
              This seller has orders sitting in the pickup window. Send them a chase before the buyer auto-refunds.
            </div>
          </div>
        </div>
        <div className="divide-y divide-red-200">
          {data.orders.map((o) => (
            <div
              key={o.id}
              className="px-4 py-3 flex items-center gap-3 flex-wrap"
              data-testid={`admin-nudge-row-${o.id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="font-medium text-neutral-900 truncate">{o.listing_title}</div>
                <div className="text-xs text-neutral-600 flex items-center gap-3 flex-wrap mt-0.5">
                  <span>Cost: <span className="font-mono">{fmt(o.reseller_wholesale_cost)}</span></span>
                  <span>Order: <span className="font-mono">{fmt(o.amount)}</span></span>
                  {o.hours_left !== null && o.hours_left !== undefined && (
                    <span className="inline-flex items-center gap-1 text-amber-700">
                      <Timer className="w-3 h-3" /> {o.hours_left}h left
                    </span>
                  )}
                  {o.nudge_count > 0 && (
                    <span className="inline-flex items-center gap-1 text-red-700 font-medium">
                      <PackageX className="w-3 h-3" /> nudged {o.nudge_count}×
                    </span>
                  )}
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => nudge(o.id)}
                disabled={busy[o.id]}
                data-testid={`admin-nudge-btn-${o.id}`}
                className="bg-[#FF211F] hover:bg-[#e01a19] text-white rounded-full"
              >
                {busy[o.id] ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Sending
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-1.5" /> Nudge seller
                  </>
                )}
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default StoreAdminNudgeBanner;
