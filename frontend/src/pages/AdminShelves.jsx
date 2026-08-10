import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { GripVertical, Save, ChevronUp, ChevronDown } from "lucide-react";

const ShelfAdmin = () => {
  const [shelves, setShelves] = useState([]);
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/admin/shelves").then((r) => setShelves(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const patch = async (id, updates) => {
    setShelves((prev) => prev.map((s) => (s.id === id ? { ...s, ...updates } : s)));
    try { await api.put(`/admin/shelves/${id}`, updates); } catch {
      toast({ title: "Update failed", variant: "destructive" });
      load();
    }
  };

  const move = (id, dir) => {
    const idx = shelves.findIndex((s) => s.id === id);
    if (idx === -1) return;
    const nxt = idx + dir;
    if (nxt < 0 || nxt >= shelves.length) return;
    const copy = [...shelves];
    [copy[idx], copy[nxt]] = [copy[nxt], copy[idx]];
    setShelves(copy);
  };

  const saveOrder = async () => {
    setSaving(true);
    try {
      await api.post("/admin/shelves/reorder", { ids: shelves.map((s) => s.id) });
      toast({ title: "Order saved" });
    } catch {
      toast({ title: "Save failed", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="admin-shelves">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold">Homepage shelves</h2>
          <p className="text-sm text-neutral-500">Reorder or hide category rows on the Home page.</p>
        </div>
        <Button onClick={saveOrder} disabled={saving} className="bg-[#FF211F] hover:bg-[#e01d1b] gap-1.5" data-testid="save-shelf-order">
          <Save className="h-4 w-4" /> {saving ? "Saving…" : "Save order"}
        </Button>
      </div>
      <div className="space-y-2">
        {shelves.map((s, i) => (
          <div key={s.id} className="flex items-center gap-3 bg-white border border-neutral-200 rounded-lg p-3" data-testid={`shelf-row-${s.id}`}>
            <GripVertical className="h-4 w-4 text-neutral-400 shrink-0" />
            <div className="flex flex-col gap-0.5 shrink-0">
              <button onClick={() => move(s.id, -1)} disabled={i === 0} className="h-5 w-5 grid place-items-center rounded hover:bg-neutral-100 disabled:opacity-30" aria-label="up"><ChevronUp className="h-3 w-3" /></button>
              <button onClick={() => move(s.id, +1)} disabled={i === shelves.length - 1} className="h-5 w-5 grid place-items-center rounded hover:bg-neutral-100 disabled:opacity-30" aria-label="down"><ChevronDown className="h-3 w-3" /></button>
            </div>
            <div className="flex-1 min-w-0 grid sm:grid-cols-[1fr_auto_auto] items-center gap-3">
              <div>
                <Input
                  value={s.title}
                  onChange={(e) => setShelves((prev) => prev.map((x) => x.id === s.id ? { ...x, title: e.target.value } : x))}
                  onBlur={(e) => patch(s.id, { title: e.target.value })}
                  className="font-semibold"
                  data-testid={`shelf-title-${s.id}`}
                />
                <div className="text-xs text-neutral-500 mt-1">
                  {s.category_slugs?.join(", ")} · limit {s.limit} · sort {s.sort_by}
                  {s.price_lte ? ` · ≤ $${s.price_lte}` : ""}
                </div>
              </div>
              <Input
                type="number" min="1" max="24"
                value={s.limit}
                onChange={(e) => patch(s.id, { limit: parseInt(e.target.value || "8", 10) })}
                className="w-20"
                data-testid={`shelf-limit-${s.id}`}
              />
              <Switch
                checked={s.enabled}
                onCheckedChange={(v) => patch(s.id, { enabled: v })}
                data-testid={`shelf-toggle-${s.id}`}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-neutral-500 mt-4">Tip: use the arrows to reorder, then click Save order. Toggle switches hide a shelf from Home instantly.</p>
    </div>
  );
};

export default ShelfAdmin;
