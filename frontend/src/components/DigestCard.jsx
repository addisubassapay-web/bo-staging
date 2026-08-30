import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Mail, TrendingDown, X } from "lucide-react";

const DigestCard = () => {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);

  const load = () => api.get("/wishlist-digest/preview").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const toggle = async (v) => {
    setData((d) => ({ ...d, opt_in: v }));
    try { await api.put("/wishlist-digest/opt", { opt_in: v }); toast({ title: v ? "Subscribed" : "Unsubscribed" }); }
    catch { load(); }
  };

  if (!data) return null;
  return (
    <div className="bg-white border border-neutral-200 rounded-xl p-4" data-testid="digest-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-lg bg-[#FFF3F2] text-[#DC2626] grid place-items-center"><Mail className="h-4 w-4" /></div>
          <div>
            <div className="font-semibold text-neutral-900">Wishlist digest</div>
            <div className="text-xs text-neutral-500">Weekly price drops on your favourites</div>
          </div>
        </div>
        <Switch checked={data.opt_in} onCheckedChange={toggle} data-testid="digest-toggle" />
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-neutral-600">
        <span>{data.drops.length} drop{data.drops.length === 1 ? "" : "s"} this week · {data.total_favorites} favourites</span>
        <button onClick={() => setOpen(true)} className="text-[#1E40AF] font-medium hover:underline" data-testid="digest-preview-btn">Preview</button>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center px-4" onClick={() => setOpen(false)}>
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="digest-preview-modal">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-xs uppercase tracking-wider text-[#1E40AF] font-semibold">Preview · BlueOcean</div>
                <h3 className="text-xl font-bold mt-1">Price drops on your wishlist</h3>
                <p className="text-sm text-neutral-500">Sent to <span className="font-mono">{data.email}</span></p>
              </div>
              <button onClick={() => setOpen(false)} className="text-neutral-500 hover:text-neutral-800"><X className="h-5 w-5" /></button>
            </div>
            <div className="mt-4 space-y-2 max-h-72 overflow-y-auto">
              {data.drops.length === 0 && <div className="text-sm text-neutral-500 py-4 text-center">No price drops this week — check back soon!</div>}
              {data.drops.map((d) => (
                <div key={d.id} className="flex items-center gap-3 border border-neutral-100 rounded-lg p-2">
                  <img src={d.images?.[0]} alt="" className="h-12 w-12 rounded object-cover bg-neutral-100" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium line-clamp-1">{d.title}</div>
                    <div className="text-xs text-neutral-500">
                      <span className="line-through">${Number(d.previous_price).toFixed(2)}</span>
                      <span className="ml-2 font-bold text-emerald-600">${Number(d.price).toFixed(2)}</span>
                    </div>
                  </div>
                  <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200"><TrendingDown className="h-3 w-3 mr-1" /> Drop</Badge>
                </div>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => toggle(false)} disabled={!data.opt_in} data-testid="digest-unsub-btn">
                Unsubscribe
              </Button>
              <Button className="flex-1 bg-[#DC2626] hover:bg-[#e01d1b]" onClick={() => setOpen(false)}>Close</Button>
            </div>
            <p className="text-[10px] text-neutral-400 mt-3 text-center">Delivery: {data.next_send}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default DigestCard;
