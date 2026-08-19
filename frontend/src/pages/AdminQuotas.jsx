import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Zap, RefreshCw, Save, Undo2 } from "lucide-react";

const AdminQuotas = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [globalCap, setGlobalCap] = useState(500);
  const [globalDraft, setGlobalDraft] = useState("500");
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState({}); // user_id → cap draft

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/scraper/admin/quota");
      setRows(data.rows || []);
      setGlobalCap(data.global_cap || 500);
      setGlobalDraft(String(data.global_cap || 500));
    } catch (e) {
      toast({ title: "Failed to load quotas", variant: "destructive" });
    } finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const saveGlobal = async () => {
    const cap = parseInt(globalDraft, 10);
    if (!cap || cap < 1) { toast({ title: "Enter a positive number", variant: "destructive" }); return; }
    try {
      await api.post("/scraper/admin/quota/global-cap", { cap });
      toast({ title: "Global cap updated", description: `${cap} credits / user / month` });
      await load();
    } catch (e) {
      toast({ title: "Save failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };

  const saveOverride = async (user_id) => {
    const raw = drafts[user_id];
    const cap = raw === "" || raw == null ? null : parseInt(raw, 10);
    try {
      await api.post("/scraper/admin/quota/override", { user_id, cap });
      toast({ title: cap ? `Override → ${cap}` : "Override cleared" });
      setDrafts((d) => { const n = { ...d }; delete n[user_id]; return n; });
      await load();
    } catch (e) {
      toast({ title: "Save failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };

  const totalUsed = useMemo(() => rows.reduce((s, r) => s + (r.used || 0), 0), [rows]);

  return (
    <div className="space-y-6" data-testid="admin-quotas-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2"><Zap className="h-6 w-6" /> Zyte quotas</h2>
          <p className="text-sm text-neutral-500 mt-1">Cap monthly Zyte credits per seller so no single user drains the plan.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="admin-quotas-refresh">
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="rounded-2xl border border-neutral-200 bg-white p-5">
        <div className="text-sm font-semibold mb-2">Global monthly cap per user</div>
        <div className="flex items-center gap-2">
          <Input
            type="number" min={1} max={1000000}
            value={globalDraft}
            onChange={(e) => setGlobalDraft(e.target.value)}
            className="w-32 h-10 tabular-nums"
            data-testid="admin-global-cap-input"
          />
          <Button onClick={saveGlobal} className="h-10 bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="admin-global-cap-save">
            <Save className="h-4 w-4 mr-1.5" /> Save
          </Button>
          <span className="text-xs text-neutral-500 ml-2">Current: <span className="font-semibold">{globalCap}</span> credits</span>
        </div>
      </div>

      <div className="rounded-2xl border border-neutral-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-neutral-100">
          <div className="text-sm font-semibold">Usage this month</div>
          <div className="text-xs text-neutral-500 tabular-nums">Total: <span className="font-semibold text-neutral-900">{totalUsed}</span> credits burned</div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-xs uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="text-left px-4 py-2.5">User</th>
              <th className="text-left px-4 py-2.5">Used</th>
              <th className="text-left px-4 py-2.5">Cap</th>
              <th className="text-left px-4 py-2.5">Override</th>
              <th className="text-left px-4 py-2.5">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-neutral-500">
                {loading ? "Loading…" : "No usage recorded yet this month."}
              </td></tr>
            )}
            {rows.map((r) => {
              const pct = r.cap ? Math.min(100, Math.round((r.used / r.cap) * 100)) : 0;
              const draft = drafts[r.user_id];
              const isDirty = draft !== undefined && draft !== "" && parseInt(draft, 10) !== r.cap;
              return (
                <tr key={r.user_id} className="border-t border-neutral-100" data-testid={`admin-quota-row-${r.user_id.slice(0,8)}`}>
                  <td className="px-4 py-3 text-xs">
                    <div className="font-medium">{r.email || "—"}</div>
                    <div className="text-neutral-500 font-mono">{r.user_id.slice(0, 12)}</div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{r.used}</td>
                  <td className="px-4 py-3 tabular-nums">{r.cap}</td>
                  <td className="px-4 py-3">
                    {r.override_active
                      ? <Badge className="bg-amber-100 text-amber-700 border-none">ON</Badge>
                      : <span className="text-xs text-neutral-400">default</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <Input
                        type="number" min={0} max={1000000}
                        value={draft ?? r.cap}
                        onChange={(e) => setDrafts((d) => ({ ...d, [r.user_id]: e.target.value }))}
                        className="w-24 h-8 tabular-nums text-xs"
                        data-testid={`admin-quota-input-${r.user_id.slice(0,8)}`}
                      />
                      <Button size="sm" variant="outline" onClick={() => saveOverride(r.user_id)} disabled={!isDirty && draft !== "0" && draft !== ""} data-testid={`admin-quota-save-${r.user_id.slice(0,8)}`}>
                        <Save className="h-3 w-3" />
                      </Button>
                      {r.override_active && (
                        <Button size="sm" variant="ghost" onClick={() => { setDrafts((d) => ({ ...d, [r.user_id]: "" })); saveOverride(r.user_id); }} title="Clear override" data-testid={`admin-quota-clear-${r.user_id.slice(0,8)}`}>
                          <Undo2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                    <div className="w-full h-1 bg-neutral-100 rounded-full mt-1.5 overflow-hidden">
                      <div className={`h-full ${pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AdminQuotas;
