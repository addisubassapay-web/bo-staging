import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { RefreshCw, AlertTriangle, CheckCircle2, Search, Wallet } from "lucide-react";

const fmt = (n) => `${n >= 0 ? "+" : "−"}$${Math.abs(Number(n) || 0).toFixed(2)}`;

const AdminLedgerAudit = () => {
  const { toast } = useToast();
  const [data, setData] = useState({ items: [], total_drifted: 0, sum_drift: 0 });
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [reconciling, setReconciling] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/wallet/audit");
      setData(data || { items: [], total_drifted: 0, sum_drift: 0 });
    } catch (e) {
      toast({ title: "Failed to load audit", description: e.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const reconcile = async (user_id, username) => {
    setReconciling((s) => ({ ...s, [user_id]: true }));
    try {
      const { data } = await api.post(`/admin/wallet/reconcile/${user_id}`);
      toast({
        title: data.reconciled ? "Wallet reconciled" : "Already in sync",
        description: data.reconciled
          ? `${username || user_id}: ${fmt(data.delta)} adjustment posted, new balance $${data.balance.toFixed(2)}`
          : `${username || user_id} is already in sync ($${data.balance.toFixed(2)})`,
      });
      await load();
    } catch (e) {
      toast({ title: "Reconcile failed", description: e.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setReconciling((s) => ({ ...s, [user_id]: false }));
    }
  };

  const filtered = q.trim()
    ? data.items.filter((r) => {
        const s = q.trim().toLowerCase();
        return (
          (r.username || "").toLowerCase().includes(s) ||
          (r.email || "").toLowerCase().includes(s) ||
          (r.user_id || "").toLowerCase().includes(s)
        );
      })
    : data.items;

  return (
    <div className="space-y-6" data-testid="admin-ledger-audit">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wallet className="h-6 w-6 text-[#FF211F]" /> Ledger audit
          </h1>
          <p className="text-sm text-neutral-500 mt-1">
            Users whose current wallet balance drifted from the sum of their transaction ledger.
            One-click reconcile posts an <code className="text-xs bg-neutral-100 px-1 rounded">adjustment</code> tx to close the gap.
          </p>
        </div>
        <Button onClick={load} variant="outline" size="sm" className="gap-1.5" data-testid="ledger-audit-refresh">
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-neutral-200 bg-white p-4">
          <div className="text-[11px] uppercase font-semibold text-neutral-400 tracking-wider">Drifted users</div>
          <div className="text-2xl font-bold text-neutral-900 tabular-nums mt-1" data-testid="drift-count">
            {loading ? "…" : data.total_drifted}
          </div>
        </div>
        <div className="rounded-xl border border-neutral-200 bg-white p-4">
          <div className="text-[11px] uppercase font-semibold text-neutral-400 tracking-wider">Net drift (all users)</div>
          <div className={`text-2xl font-bold tabular-nums mt-1 ${data.sum_drift === 0 ? "text-emerald-700" : "text-amber-600"}`} data-testid="drift-net">
            {loading ? "…" : `${fmt(data.sum_drift)}`}
          </div>
        </div>
        <div className="rounded-xl border border-neutral-200 bg-white p-4 col-span-2 sm:col-span-1">
          <div className="text-[11px] uppercase font-semibold text-neutral-400 tracking-wider">Status</div>
          <div className="text-sm font-semibold mt-2 flex items-center gap-1.5">
            {data.total_drifted === 0 ? (
              <><CheckCircle2 className="h-4 w-4 text-emerald-600" /> <span className="text-emerald-700">All wallets in sync</span></>
            ) : (
              <><AlertTriangle className="h-4 w-4 text-amber-500" /> <span className="text-amber-700">Attention needed</span></>
            )}
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by username, email, or user id…"
          className="pl-9 h-11"
          data-testid="ledger-audit-search"
        />
      </div>

      {/* Table */}
      {loading ? (
        <div className="py-10 text-center text-sm text-neutral-500">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-200 bg-neutral-50 p-10 text-center">
          <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto" />
          <div className="mt-2 font-semibold text-neutral-800">All wallets are in sync</div>
          <div className="text-sm text-neutral-500 mt-1">No drift detected between stored balances and the transaction ledger.</div>
        </div>
      ) : (
        <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left px-4 py-3 font-semibold">User</th>
                  <th className="text-right px-4 py-3 font-semibold">Current balance</th>
                  <th className="text-right px-4 py-3 font-semibold">Expected (ledger)</th>
                  <th className="text-right px-4 py-3 font-semibold">Drift</th>
                  <th className="text-right px-4 py-3 font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {filtered.map((r) => (
                  <tr key={r.user_id} data-testid={`ledger-row-${r.user_id}`}>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-neutral-900">{r.username || r.user_id}</div>
                      <div className="text-xs text-neutral-500 truncate max-w-[240px]">{r.email}</div>
                    </td>
                    <td className="text-right px-4 py-3 font-mono tabular-nums">${r.current_balance.toFixed(2)}</td>
                    <td className="text-right px-4 py-3 font-mono tabular-nums text-neutral-500">${r.expected_balance.toFixed(2)}</td>
                    <td className={`text-right px-4 py-3 font-mono font-bold tabular-nums ${r.drift > 0 ? "text-amber-600" : "text-red-600"}`}>{fmt(r.drift)}</td>
                    <td className="text-right px-4 py-3">
                      <Button
                        size="sm"
                        onClick={() => reconcile(r.user_id, r.username)}
                        disabled={reconciling[r.user_id]}
                        className="gap-1.5 h-8 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110"
                        data-testid={`reconcile-btn-${r.user_id}`}
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${reconciling[r.user_id] ? "animate-spin" : ""}`} />
                        {reconciling[r.user_id] ? "…" : "Reconcile"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminLedgerAudit;
