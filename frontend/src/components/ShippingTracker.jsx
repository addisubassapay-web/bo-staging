import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Truck, Package, MapPin, CheckCircle2, Clock, Printer } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const STATUS_LABELS = {
  label_created: { label: "Label created", icon: Package, tone: "bg-slate-100 text-slate-700" },
  picked_up: { label: "Picked up", icon: Truck, tone: "bg-blue-100 text-blue-700" },
  in_transit: { label: "In transit", icon: Truck, tone: "bg-blue-100 text-blue-700" },
  out_for_delivery: { label: "Out for delivery", icon: MapPin, tone: "bg-amber-100 text-amber-800" },
  delivered: { label: "Delivered", icon: CheckCircle2, tone: "bg-emerald-100 text-emerald-800" },
};

/**
 * ShippingTracker
 * - Displays label status + events for a given order.
 * - If `canPurchase` (seller view) and no label yet, shows a "Buy label" button.
 */
const ShippingTracker = ({ orderId, canPurchase = false, canAdvance = false }) => {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(false);
  const [advancing, setAdvancing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get(`/orders/${orderId}/tracking`);
      setData(d);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, [orderId]);

  const buyLabel = async () => {
    setBuying(true);
    try {
      await api.post(`/orders/${orderId}/shipping-label`);
      toast({ title: "Label created", description: "Tracking info generated (mocked)" });
      await load();
    } catch (err) {
      toast({ title: "Could not create label", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setBuying(false);
    }
  };

  const advance = async () => {
    setAdvancing(true);
    try {
      const { data: r } = await api.post(`/orders/${orderId}/shipping-advance`, {});
      toast({ title: `Advanced to ${r.current_status.replace(/_/g, " ")}` });
      await load();
    } catch (err) {
      toast({ title: "Could not advance", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setAdvancing(false);
    }
  };

  if (loading) return null;
  if (!data || !data.has_label) {
    if (canPurchase) {
      return (
        <div className="mt-3 flex items-center justify-between bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2" data-testid={`tracker-empty-${orderId}`}>
          <div className="text-sm text-neutral-600 flex items-center gap-2">
            <Truck className="h-4 w-4" /> No shipping label yet
          </div>
          <Button size="sm" variant="outline" onClick={buyLabel} disabled={buying} data-testid={`buy-label-${orderId}`}>
            {buying ? "Creating…" : "Buy label (mock)"}
          </Button>
        </div>
      );
    }
    return null;
  }

  const cur = STATUS_LABELS[data.current_status] || STATUS_LABELS.label_created;
  const CurIcon = cur.icon;
  return (
    <div className="mt-3 border border-neutral-200 rounded-lg p-3" data-testid={`tracker-${orderId}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Badge className={`${cur.tone} border-transparent`}><CurIcon className="h-3 w-3 mr-1" />{cur.label}</Badge>
          <span className="text-sm font-mono text-neutral-700" data-testid={`tracking-num-${orderId}`}>{data.tracking_number}</span>
          <span className="text-xs text-neutral-500">via {data.carrier}</span>
        </div>
        <div className="text-xs text-neutral-500">
          {data.estimated_delivery && <>ETA {data.estimated_delivery}</>}
        </div>
      </div>
      <div className="mt-2 flex justify-end gap-2 flex-wrap">
        {data.tracking_number && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              const t = localStorage.getItem("mercari_token") || "";
              window.open(
                `${process.env.REACT_APP_BACKEND_URL}/api/orders/${orderId}/label.svg?auth=${encodeURIComponent(t)}`,
                "_blank",
              );
            }}
            className="gap-1.5"
            data-testid={`view-label-${orderId}`}
          >
            <Printer className="h-3.5 w-3.5" /> Print label
          </Button>
        )}
        {canAdvance && data.current_status !== "delivered" && (
          <Button size="sm" variant="outline" onClick={advance} disabled={advancing} data-testid={`advance-${orderId}`}>
            {advancing ? "Advancing…" : "Mark next stage →"}
          </Button>
        )}
      </div>
      <div className="mt-3 space-y-2">
        {data.events.slice().reverse().map((e, i) => {
          const s = STATUS_LABELS[e.status] || STATUS_LABELS.label_created;
          const Icon = s.icon;
          return (
            <div key={i} className="flex items-start gap-3 text-sm">
              <div className={`mt-0.5 h-6 w-6 rounded-full grid place-items-center ${i === 0 ? s.tone : "bg-neutral-100 text-neutral-500"}`}>
                <Icon className="h-3.5 w-3.5" />
              </div>
              <div className="flex-1">
                <div className="text-neutral-800">{e.description}</div>
                <div className="text-xs text-neutral-500 flex items-center gap-2">
                  <Clock className="h-3 w-3" />{new Date(e.at).toLocaleString()} · {e.location}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ShippingTracker;
