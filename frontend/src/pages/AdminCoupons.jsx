import React, { useCallback, useEffect, useState } from "react";
import { Ticket, Plus, Save, Trash2, Percent, Boxes } from "lucide-react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";

const emptyForm = {
  code: "",
  percent: 10,
  max_off: 20,
  min_subtotal: 0,
  tier: false,
  description: "",
  active: true,
};

const CouponRow = ({ coupon, onSave, onDelete }) => {
  const [form, setForm] = useState(coupon);
  const [saving, setSaving] = useState(false);

  useEffect(() => setForm(coupon), [coupon]);

  const save = async () => {
    setSaving(true);
    try { await onSave(coupon.id, form); } finally { setSaving(false); }
  };

  return (
    <div className="grid grid-cols-12 gap-2 items-center px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900" data-testid={`coupon-row-${coupon.code}`}>
      <div className="col-span-2">
        <div className="font-mono uppercase font-bold text-sm tracking-wider text-neutral-900 dark:text-neutral-100">{coupon.code}</div>
        <div className="text-[10px] uppercase tracking-widest text-neutral-500">
          {coupon.tier ? "TIER" : "%"}
        </div>
      </div>
      <div className="col-span-1">
        <Input type="number" step="0.01" value={form.percent} onChange={(e) => setForm({ ...form, percent: parseFloat(e.target.value) || 0 })} className="h-9" disabled={form.tier} />
      </div>
      <div className="col-span-1">
        <Input type="number" step="0.01" value={form.max_off} onChange={(e) => setForm({ ...form, max_off: parseFloat(e.target.value) || 0 })} className="h-9" disabled={form.tier} />
      </div>
      <div className="col-span-1">
        <Input type="number" step="0.01" value={form.min_subtotal} onChange={(e) => setForm({ ...form, min_subtotal: parseFloat(e.target.value) || 0 })} className="h-9" disabled={form.tier} />
      </div>
      <div className="col-span-4">
        <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description" className="h-9" />
      </div>
      <div className="col-span-1 flex items-center gap-2">
        <Switch checked={form.active} onCheckedChange={(v) => setForm({ ...form, active: v })} data-testid={`coupon-active-${coupon.code}`} />
      </div>
      <div className="col-span-2 flex gap-2 justify-end">
        <Button size="sm" onClick={save} disabled={saving} className="h-9 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110 text-white" data-testid={`coupon-save-${coupon.code}`}>
          <Save className="h-3.5 w-3.5 mr-1" /> {saving ? "…" : "Save"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => onDelete(coupon.id, coupon.code)} className="h-9 text-red-600 hover:bg-red-50" data-testid={`coupon-delete-${coupon.code}`}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
};

const AdminCoupons = () => {
  const { toast } = useToast();
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/coupons");
      setCoupons(data || []);
    } catch (err) {
      toast({ title: "Failed to load coupons", description: err.response?.data?.detail, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.code.trim()) { toast({ title: "Enter a code", variant: "destructive" }); return; }
    setCreating(true);
    try {
      await api.post("/admin/coupons", { ...form, code: form.code.trim().toUpperCase() });
      toast({ title: `Coupon ${form.code.toUpperCase()} created` });
      setForm(emptyForm);
      await load();
    } catch (err) {
      toast({ title: "Create failed", description: err.response?.data?.detail, variant: "destructive" });
    } finally { setCreating(false); }
  };

  const save = async (id, payload) => {
    try {
      await api.put(`/admin/coupons/${id}`, payload);
      toast({ title: "Saved" });
      await load();
    } catch (err) {
      toast({ title: "Save failed", description: err.response?.data?.detail, variant: "destructive" });
    }
  };

  const remove = async (id, code) => {
    if (!window.confirm(`Delete coupon ${code}?`)) return;
    try {
      await api.delete(`/admin/coupons/${id}`);
      toast({ title: `Deleted ${code}` });
      await load();
    } catch (err) {
      toast({ title: "Delete failed", description: err.response?.data?.detail, variant: "destructive" });
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      <div className="flex items-center gap-3 mb-2">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[#7DD3FC] to-[#2563EB] grid place-items-center text-white">
          <Ticket className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">Coupons</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Add, tune, and toggle discount codes without a deploy.</p>
        </div>
      </div>

      {/* Create form */}
      <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
        <div className="flex items-center gap-2 font-semibold mb-3 text-neutral-900 dark:text-neutral-100">
          <Plus className="h-4 w-4" /> New coupon
        </div>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <div>
            <Label>Code</Label>
            <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="SUMMER20" className="mt-1 uppercase font-mono" data-testid="new-coupon-code" />
          </div>
          <div>
            <Label className="flex items-center gap-1"><Percent className="h-3 w-3" /> Percent</Label>
            <Input type="number" step="0.01" value={form.percent} onChange={(e) => setForm({ ...form, percent: parseFloat(e.target.value) || 0 })} className="mt-1" disabled={form.tier} />
          </div>
          <div>
            <Label>Max off ($)</Label>
            <Input type="number" step="0.01" value={form.max_off} onChange={(e) => setForm({ ...form, max_off: parseFloat(e.target.value) || 0 })} className="mt-1" disabled={form.tier} />
          </div>
          <div>
            <Label>Min subtotal</Label>
            <Input type="number" step="0.01" value={form.min_subtotal} onChange={(e) => setForm({ ...form, min_subtotal: parseFloat(e.target.value) || 0 })} className="mt-1" disabled={form.tier} />
          </div>
          <div className="md:col-span-2">
            <Label>Description</Label>
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Shown to buyers at checkout" className="mt-1" />
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <Boxes className="h-4 w-4 text-[#2563EB]" />
            <Switch checked={form.tier} onCheckedChange={(v) => setForm({ ...form, tier: v })} data-testid="new-coupon-tier" />
            Wholesale tier (auto: 5+ items 5%, 10+ items 10%)
          </label>
          <Button onClick={create} disabled={creating} className="bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white" data-testid="new-coupon-create">
            <Plus className="h-4 w-4 mr-1" /> {creating ? "Creating…" : "Create coupon"}
          </Button>
        </div>
      </div>

      {/* Existing coupons */}
      <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950/50 p-5">
        <div className="grid grid-cols-12 gap-2 text-[11px] uppercase tracking-widest text-neutral-500 dark:text-neutral-400 mb-3 px-3">
          <div className="col-span-2">Code</div>
          <div className="col-span-1">%</div>
          <div className="col-span-1">Max</div>
          <div className="col-span-1">Min</div>
          <div className="col-span-4">Description</div>
          <div className="col-span-1">Active</div>
          <div className="col-span-2 text-right">Actions</div>
        </div>
        <div className="space-y-2">
          {loading && <div className="p-8 text-center text-neutral-400">Loading…</div>}
          {!loading && coupons.length === 0 && <div className="p-8 text-center text-neutral-400">No coupons yet — create one above.</div>}
          {coupons.map((c) => (
            <CouponRow key={c.id} coupon={c} onSave={save} onDelete={remove} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default AdminCoupons;
