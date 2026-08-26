import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Sparkles, Rocket, Trash2, Loader2, RefreshCw } from "lucide-react";

const TIER_COLOR = { bronze: "bg-amber-100 text-amber-800", silver: "bg-slate-200 text-slate-800", gold: "bg-yellow-100 text-yellow-800 border border-yellow-400" };

const AdminStoreBoosts = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(null);
  const [form, setForm] = useState({ store_id: "", tier: "gold", category_id: "", days: 14, reason: "" });
  const [stores, setStores] = useState([]);
  const [storeSearch, setStoreSearch] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [b, c] = await Promise.all([
        api.get("/admin/store-boosts?active_only=false"),
        api.get("/categories"),
      ]);
      setRows(b.data.items || []);
      setCategories(c.data || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (storeSearch.length < 2) { setStores([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/stores-search", { params: { q: storeSearch, limit: 10, include_inactive: true } });
        setStores(data.items || []);
      } catch { /* ignore */ }
    }, 250);
    return () => clearTimeout(t);
  }, [storeSearch]);

  const grant = async () => {
    if (!form.store_id) { toast({ title: "Pick a store", variant: "destructive" }); return; }
    setBusy("grant");
    try {
      await api.post("/admin/store-boost", {
        store_id: form.store_id, tier: form.tier,
        category_id: form.category_id || null,
        days: Number(form.days) || 7,
        reason: form.reason || null,
      });
      toast({ title: `${form.tier} boost granted for ${form.days} days` });
      setForm({ ...form, store_id: "", reason: "" });
      setStoreSearch("");
      setStores([]);
      await load();
    } catch (e) {
      toast({ title: "Grant failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setBusy(null); }
  };

  const revoke = async (storeId, boostId) => {
    if (!window.confirm("Revoke this boost?")) return;
    setBusy(boostId);
    try {
      await api.post("/admin/store-boost/revoke", { store_id: storeId, boost_id: boostId });
      await load();
    } catch { toast({ title: "Revoke failed", variant: "destructive" }); }
    finally { setBusy(null); }
  };

  return (
    <div className="space-y-6" data-testid="admin-store-boosts-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2"><Rocket className="h-6 w-6" /> Store boosts</h2>
          <p className="text-sm text-neutral-500 mt-1">Grant complimentary boosts to VIP sellers or fix goodwill without payment.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="admin-boosts-refresh">
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="rounded-2xl border border-neutral-200 bg-white p-5 space-y-3" data-testid="admin-boost-grant-form">
        <div className="text-sm font-semibold flex items-center gap-2"><Sparkles className="h-4 w-4 text-amber-500" /> Grant a complimentary boost</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Find store</Label>
            <Input
              value={storeSearch}
              onChange={(e) => setStoreSearch(e.target.value)}
              placeholder="Type store name…"
              className="mt-1 h-10"
              data-testid="admin-boost-store-search"
            />
            {stores.length > 0 && (
              <div className="mt-1 border border-neutral-200 rounded-lg bg-white max-h-48 overflow-y-auto">
                {stores.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => { setForm({ ...form, store_id: s.id }); setStoreSearch(s.name); setStores([]); }}
                    className="w-full text-left px-3 py-2 hover:bg-neutral-50 text-xs flex justify-between items-center"
                    data-testid={`admin-boost-pick-${s.slug || s.id.slice(0,8)}`}
                  >
                    <span className="truncate">{s.name}</span>
                    <span className="text-neutral-500 tabular-nums">{s.followers_count || 0} followers</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div>
            <Label className="text-xs">Tier</Label>
            <Select value={form.tier} onValueChange={(v) => setForm({ ...form, tier: v })}>
              <SelectTrigger className="mt-1 h-10" data-testid="admin-boost-tier"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="bronze">Bronze (1× score)</SelectItem>
                <SelectItem value="silver">Silver (2× score)</SelectItem>
                <SelectItem value="gold">Gold (3× score)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Category (optional — global if empty)</Label>
            <Select value={form.category_id || "__all__"} onValueChange={(v) => setForm({ ...form, category_id: v === "__all__" ? "" : v })}>
              <SelectTrigger className="mt-1 h-10" data-testid="admin-boost-category"><SelectValue placeholder="Global boost" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Global (all categories)</SelectItem>
                {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Duration (days, 1-180)</Label>
            <Input
              type="number" min={1} max={180}
              value={form.days}
              onChange={(e) => setForm({ ...form, days: e.target.value })}
              className="mt-1 h-10 tabular-nums"
              data-testid="admin-boost-days"
            />
          </div>
        </div>
        <div>
          <Label className="text-xs">Reason / note (optional)</Label>
          <Input
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
            placeholder="e.g. Onboarding perk for verified brand"
            className="mt-1 h-10"
            data-testid="admin-boost-reason"
          />
        </div>
        <Button
          onClick={grant}
          disabled={busy === "grant" || !form.store_id}
          className="bg-emerald-600 hover:bg-emerald-700"
          data-testid="admin-boost-grant-btn"
        >
          {busy === "grant" ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Granting…</> : <><Rocket className="h-4 w-4 mr-1.5" /> Grant boost</>}
        </Button>
      </div>

      <div className="rounded-2xl border border-neutral-200 bg-white overflow-hidden">
        <div className="p-4 border-b border-neutral-100 text-sm font-semibold">Active boosts ({rows.length})</div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[720px]">
          <thead className="bg-neutral-50 text-xs uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="text-left px-4 py-2.5">Store</th>
              <th className="text-left px-4 py-2.5">Tier</th>
              <th className="text-left px-4 py-2.5">Scope</th>
              <th className="text-left px-4 py-2.5">Source</th>
              <th className="text-left px-4 py-2.5">Expires</th>
              <th className="text-left px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-neutral-500">{loading ? "Loading…" : "No active boosts."}</td></tr>
            )}
            {rows.flatMap((s) => (s.boosts || []).map((b) => ({ ...b, store_id: s.id, store_name: s.name, store_slug: s.slug }))).map((b) => (
              <tr key={b.id} className="border-t border-neutral-100" data-testid={`admin-boost-row-${b.id.slice(0,8)}`}>
                <td className="px-4 py-3 text-xs font-medium">{b.store_name}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${TIER_COLOR[b.tier] || ""}`}>{b.tier}</span>
                </td>
                <td className="px-4 py-3 text-xs">{b.category_id ? "Category" : "Global"}</td>
                <td className="px-4 py-3">
                  {b.source === "paid"
                    ? <Badge className="bg-emerald-100 text-emerald-700 border-none text-[10px]">paid ${b.price_paid}</Badge>
                    : <Badge className="bg-sky-100 text-sky-700 border-none text-[10px]">admin comp</Badge>}
                </td>
                <td className="px-4 py-3 text-xs tabular-nums">{b.expires_at ? new Date(b.expires_at).toLocaleDateString() : "—"}</td>
                <td className="px-4 py-3">
                  <Button variant="ghost" size="sm" onClick={() => revoke(b.store_id, b.id)} disabled={busy === b.id} data-testid={`admin-boost-revoke-${b.id.slice(0,8)}`}>
                    {busy === b.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3 text-red-500" />}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
};

export default AdminStoreBoosts;
