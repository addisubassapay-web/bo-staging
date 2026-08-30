import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, ShoppingCart, Send, Bell, PackageCheck, PackageX, Timer } from "lucide-react";

/**
 * PickupTimelineDialog — chronological audit trail of every pickup-related
 * event fired for an order: created → reminders (T-6h/T-1h) → admin nudges →
 * picked / auto_cancelled. Admin-only endpoint.
 */
const iconFor = (type) => {
  switch (type) {
    case "order_created": return <ShoppingCart className="w-3.5 h-3.5 text-neutral-500" />;
    case "reminder":      return <Bell className="w-3.5 h-3.5 text-amber-600" />;
    case "admin_nudge":   return <Send className="w-3.5 h-3.5 text-red-600" />;
    case "picked":        return <PackageCheck className="w-3.5 h-3.5 text-emerald-600" />;
    case "auto_cancelled":return <PackageX className="w-3.5 h-3.5 text-red-700" />;
    default:              return <Timer className="w-3.5 h-3.5 text-neutral-400" />;
  }
};

const labelFor = (e) => {
  switch (e.type) {
    case "order_created":  return "Order placed by buyer";
    case "reminder":       return `Reminder sent · ${e.hours_before}h before deadline`;
    case "admin_nudge":    return `Admin nudge sent${e.admin_email ? ` by ${e.admin_email}` : ""}`;
    case "picked":         return `Seller picked · available $${(e.paid_from_available ?? 0).toFixed(2)} + frozen $${(e.paid_from_frozen ?? 0).toFixed(2)}`;
    case "auto_cancelled": return `Auto-cancelled · ${e.reason || "deadline expired"}`;
    default:               return e.type;
  }
};

const fmtDate = (v) => {
  if (!v) return "";
  try {
    const d = typeof v === "string" ? new Date(v) : v;
    return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return String(v);
  }
};

const PickupTimelineDialog = ({ orderId, open, onClose }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !orderId) return;
    setLoading(true);
    api
      .get(`/admin/orders/${orderId}/pickup-timeline`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [open, orderId]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className="max-w-lg" data-testid="pickup-timeline-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Timer className="w-5 h-5 text-[#DC2626]" /> Pickup timeline
          </DialogTitle>
        </DialogHeader>
        {loading || !data ? (
          <div className="py-8 text-center text-neutral-500 text-sm">
            <Loader2 className="w-5 h-5 animate-spin inline mr-2" /> Loading timeline…
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-sm">
              <div className="font-medium text-neutral-900">{data.listing_title}</div>
              <div className="text-xs text-neutral-500">
                Status: <span className="font-semibold">{data.fulfillment_status}</span> · Nudges: {data.nudge_count || 0}
              </div>
            </div>
            <div className="relative pl-5 border-l border-neutral-200">
              {(data.events || []).map((e, i) => (
                <div key={i} className="pb-3 last:pb-0 relative" data-testid={`timeline-event-${e.type}-${i}`}>
                  <div className="absolute -left-[27px] top-0.5 w-5 h-5 rounded-full bg-white border border-neutral-200 flex items-center justify-center">
                    {iconFor(e.type)}
                  </div>
                  <div className="text-sm font-medium text-neutral-900">{labelFor(e)}</div>
                  <div className="text-[11px] text-neutral-500 mt-0.5">{fmtDate(e.at)}</div>
                  {e.message && (
                    <div className="text-xs text-neutral-600 bg-neutral-50 border border-neutral-200 rounded-md p-2 mt-1 italic">
                      &ldquo;{e.message}&rdquo;
                    </div>
                  )}
                </div>
              ))}
              {(!data.events || data.events.length === 0) && (
                <div className="text-sm text-neutral-500">No events recorded yet.</div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default PickupTimelineDialog;
