import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { GripVertical, Save } from "lucide-react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";

const ShelfAdmin = () => {
  const [shelves, setShelves] = useState([]);
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = () => api.get("/admin/shelves").then((r) => setShelves(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const patch = async (id, updates) => {
    setShelves((prev) => prev.map((s) => (s.id === id ? { ...s, ...updates } : s)));
    try { await api.put(`/admin/shelves/${id}`, updates); } catch {
      toast({ title: "Update failed", variant: "destructive" });
      load();
    }
  };

  const onDragEnd = (result) => {
    if (!result.destination || result.source.index === result.destination.index) return;
    const copy = [...shelves];
    const [moved] = copy.splice(result.source.index, 1);
    copy.splice(result.destination.index, 0, moved);
    setShelves(copy);
    setDirty(true);
  };

  const saveOrder = async () => {
    setSaving(true);
    try {
      await api.post("/admin/shelves/reorder", { ids: shelves.map((s) => s.id) });
      toast({ title: "Order saved" });
      setDirty(false);
    } catch {
      toast({ title: "Save failed", variant: "destructive" });
    } finally { setSaving(false); }
  };

  return (
    <div data-testid="admin-shelves">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold">Homepage shelves</h2>
          <p className="text-sm text-neutral-500">Drag to reorder, toggle to hide.</p>
        </div>
        <Button onClick={saveOrder} disabled={saving || !dirty} className="bg-[#FF211F] hover:bg-[#e01d1b] gap-1.5 disabled:opacity-40" data-testid="save-shelf-order">
          <Save className="h-4 w-4" /> {saving ? "Saving…" : dirty ? "Save order" : "Saved"}
        </Button>
      </div>
      <DragDropContext onDragEnd={onDragEnd}>
        <Droppable droppableId="shelves">
          {(provided) => (
            <div ref={provided.innerRef} {...provided.droppableProps} className="space-y-2">
              {shelves.map((s, i) => (
                <Draggable key={s.id} draggableId={s.id} index={i}>
                  {(prov, snapshot) => (
                    <div
                      ref={prov.innerRef}
                      {...prov.draggableProps}
                      className={`flex items-center gap-3 bg-white border rounded-lg p-3 ${snapshot.isDragging ? "border-[#FF7A18] shadow-lg" : "border-neutral-200"}`}
                      data-testid={`shelf-row-${s.id}`}
                    >
                      <span {...prov.dragHandleProps} className="cursor-grab active:cursor-grabbing text-neutral-400 hover:text-neutral-600" data-testid={`shelf-drag-${s.id}`}>
                        <GripVertical className="h-4 w-4" />
                      </span>
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
                            {s.price_lte ? ` · <= $${s.price_lte}` : ""}
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
                  )}
                </Draggable>
              ))}
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>
      <p className="text-xs text-neutral-500 mt-4">Drag rows to reorder, then Save. Toggle switches hide a shelf from Home instantly.</p>
    </div>
  );
};

export default ShelfAdmin;
