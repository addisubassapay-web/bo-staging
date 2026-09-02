import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  Mail, RefreshCw, Search, CheckCircle2, XCircle, Clock, BarChart3, Filter,
} from "lucide-react";

/**
 * AdminDeliverability — read-only browser for db.email_delivery_log.
 * Polls /admin/mail/delivery-log with kind + status + q filters, renders
 * the 24h provider × status breakdown as stat cards, and lists recent
 * sends with copy-to-clipboard message IDs.
 *
 * Not a mutation surface — no delete/replay. Suppression/unsubscribe
 * live in the existing Suppression List admin page.
 */
const KIND_TONE = {
  auth: "bg-red-100 text-red-800",
  receipts: "bg-emerald-100 text-emerald-800",
  marketing: "bg-amber-100 text-amber-800",
  seller: "bg-indigo-100 text-indigo-800",
  support: "bg-neutral-100 text-neutral-800",
  system: "bg-neutral-100 text-neutral-700",
};

const AdminDeliverability = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [breakdown, setBreakdown] = useState({});
  const [loading, setLoading] = useState(false);
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");

  const load = () => {
    setLoading(true);
    const params = { limit: 200 };
    if (kind !== "all") params.kind = kind;
    if (status !== "all") params.status = status;
    if (q.trim()) params.q = q.trim();
    api.get("/admin/mail/delivery-log", { params })
      .then((r) => {
        setRows(r.data.items || []);
        setBreakdown(r.data.last_24h_breakdown || {});
      })
      .catch((e) => toast({
        title: "Failed to load delivery log",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      }))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 24h totals for the stat cards
  const totals = useMemo(() => {
    let sent = 0, failed = 0, providers = {};
    Object.entries(breakdown).forEach(([prov, byStatus]) => {
      providers[prov] = 0;
      Object.entries(byStatus || {}).forEach(([st, n]) => {
        providers[prov] += n;
        if (st === "sent") sent += n;
        else failed += n;
      });
    });
    const total = sent + failed;
    const rate = total === 0 ? "—" : `${Math.round((sent / total) * 100)}%`;
    return { sent, failed, total, rate, providers };
  }, [breakdown]);

  const copy = (text) => {
    if (!text) return;
    navigator.clipboard?.writeText(text).then(
      () => toast({ title: "Copied", description: text.slice(0, 40) }),
      () => {},
    );
  };

  return (
    <div className="space-y-6" data-testid="admin-deliverability-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Mail className="h-6 w-6" /> Deliverability log
          </h2>
          <p className="text-sm text-neutral-500 mt-1 max-w-2xl">
            Every outbound email — Resend primary + Hostinger fallback — is
            recorded here with provider, message ID, and status. Use the
            filters to audit a specific kind or hunt down a failure.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="deliv-refresh">
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {/* 24h stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider flex items-center gap-1"><BarChart3 className="h-3.5 w-3.5" /> Sent (24h)</div>
          <div className="text-2xl font-bold mt-1 text-emerald-600" data-testid="deliv-stat-sent">{totals.sent}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Failed (24h)</div>
          <div className="text-2xl font-bold mt-1 text-red-600" data-testid="deliv-stat-failed">{totals.failed}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Success rate</div>
          <div className="text-2xl font-bold mt-1" data-testid="deliv-stat-rate">{totals.rate}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Providers used</div>
          <div className="mt-1 flex flex-wrap gap-1" data-testid="deliv-stat-providers">
            {Object.entries(totals.providers).length === 0
              ? <span className="text-neutral-400 text-sm">—</span>
              : Object.entries(totals.providers).map(([p, n]) => (
                  <Badge key={p} variant="secondary" className="text-[10px]">{p}: {n}</Badge>
                ))}
          </div>
        </div>
      </div>

      {/* Filters */}
      <form onSubmit={(e) => { e.preventDefault(); load(); }} className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <Input placeholder="Search recipient or subject…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" data-testid="deliv-search" />
        </div>
        <Select value={kind} onValueChange={(v) => { setKind(v); setTimeout(load, 0); }}>
          <SelectTrigger className="w-40" data-testid="deliv-kind"><SelectValue placeholder="All kinds" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All kinds</SelectItem>
            <SelectItem value="auth">auth</SelectItem>
            <SelectItem value="receipts">receipts</SelectItem>
            <SelectItem value="marketing">marketing</SelectItem>
            <SelectItem value="seller">seller</SelectItem>
            <SelectItem value="support">support</SelectItem>
            <SelectItem value="system">system</SelectItem>
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={(v) => { setStatus(v); setTimeout(load, 0); }}>
          <SelectTrigger className="w-36" data-testid="deliv-status"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="sent">Sent</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" size="sm" variant="outline" data-testid="deliv-apply"><Filter className="h-4 w-4 mr-1.5" /> Apply</Button>
      </form>

      {/* Rows */}
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-3 py-3">Sent at</th>
                <th className="text-left px-3 py-3">Kind</th>
                <th className="text-left px-3 py-3">Provider</th>
                <th className="text-left px-3 py-3">Status</th>
                <th className="text-left px-3 py-3">Recipient</th>
                <th className="text-left px-3 py-3">Subject</th>
                <th className="text-left px-3 py-3">Message ID / Error</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-neutral-500">
                  {loading ? "Loading…" : "No delivery entries match this filter yet."}
                </td></tr>
              )}
              {rows.map((r) => {
                const ok = r.status === "sent";
                return (
                  <tr key={r.id} className="border-t border-neutral-100 dark:border-neutral-800" data-testid={`deliv-row-${r.id}`}>
                    <td className="px-3 py-3 text-xs text-neutral-500 tabular-nums whitespace-nowrap">
                      {r.at ? new Date(r.at).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-3">
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${KIND_TONE[r.kind] || KIND_TONE.system}`}>{r.kind || "system"}</span>
                    </td>
                    <td className="px-3 py-3 text-xs font-mono">{r.provider || "—"}</td>
                    <td className="px-3 py-3">
                      {ok
                        ? <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-semibold"><CheckCircle2 className="h-3.5 w-3.5" /> sent</span>
                        : <span className="inline-flex items-center gap-1 text-red-700 text-xs font-semibold"><XCircle className="h-3.5 w-3.5" /> failed</span>}
                    </td>
                    <td className="px-3 py-3 text-xs font-mono truncate max-w-[220px]" title={r.to}>{r.to}</td>
                    <td className="px-3 py-3 text-xs truncate max-w-[280px]" title={r.subject}>{r.subject}</td>
                    <td className="px-3 py-3 text-[11px] font-mono">
                      {ok ? (
                        r.message_id ? (
                          <button onClick={() => copy(r.message_id)} className="text-indigo-600 hover:underline truncate max-w-[180px] inline-block" title="Copy message ID" data-testid={`deliv-msgid-${r.id}`}>
                            {r.message_id.slice(0, 12)}…
                          </button>
                        ) : "—"
                      ) : (
                        <span className="text-red-600 truncate max-w-[280px] inline-block" title={r.error}>{(r.error || "").slice(0, 60)}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="text-xs text-neutral-500 flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> Showing {rows.length} rows · click a message ID to copy it</div>
    </div>
  );
};

export default AdminDeliverability;
