import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Mail, RefreshCw, Send, AlertCircle, CheckCircle2, Filter } from "lucide-react";

const KINDS = ["", "order", "sale", "wallet", "payout", "dispute", "system", "admin_test", "newsletter"];

const AdminEmailLog = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [kind, setKind] = useState("");
  const [showFailedOnly, setShowFailedOnly] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [sending, setSending] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (kind) params.kind = kind;
      const { data } = await api.get("/admin/email/log", { params });
      setRows(data.items || []);
    } catch (e) {
      toast({ title: "Failed to load email log", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(
    () => (showFailedOnly ? rows.filter((r) => r.ok === false) : rows),
    [rows, showFailedOnly],
  );

  const failedCount = useMemo(() => rows.filter((r) => r.ok === false).length, [rows]);

  const sendTest = async () => {
    if (!testTo || !testTo.includes("@")) {
      toast({ title: "Enter a valid email", variant: "destructive" });
      return;
    }
    setSending(true);
    try {
      const { data } = await api.post("/admin/email/test", { to: testTo });
      if (data.ok) {
        toast({ title: "Test email sent", description: `Provider: ${data.provider}` });
      } else {
        toast({ title: "Send failed", description: data.error || "Unknown error", variant: "destructive" });
      }
      await load();
    } catch (e) {
      toast({ title: "Send failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-email-log-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Mail className="h-6 w-6" /> Email delivery log
          </h2>
          <p className="text-sm text-neutral-500 mt-1">
            All outbound transactional emails. Failed sends (SMTP errors, bounces) show a red pill so you can spot delivery issues quickly.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {failedCount > 0 && (
            <Badge variant="destructive" className="rounded-full px-3" data-testid="admin-email-failed-count">
              {failedCount} failed
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="admin-email-refresh">
            <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Test send */}
      <div className="rounded-xl border border-neutral-200 bg-white p-4">
        <div className="flex items-center gap-2 mb-3">
          <Send className="h-4 w-4 text-neutral-600" />
          <div className="font-semibold">Send a test email</div>
        </div>
        <p className="text-xs text-neutral-500 mb-3">
          Verifies the Hostinger SMTP pipeline is live end-to-end. The result is recorded in the log below with tag <code className="text-[10px] bg-neutral-100 px-1 rounded">admin_test</code>.
        </p>
        <div className="flex gap-2 flex-wrap">
          <Input
            type="email"
            placeholder="recipient@example.com"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            className="max-w-sm"
            data-testid="admin-email-test-to"
          />
          <Button onClick={sendTest} disabled={sending} className="bg-[#DC2626] hover:bg-[#e01d1b]" data-testid="admin-email-test-send">
            {sending ? "Sending…" : "Send test"}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-neutral-500" />
          <span className="text-sm text-neutral-600">Kind</span>
          <Select value={kind || "__all__"} onValueChange={(v) => setKind(v === "__all__" ? "" : v)}>
            <SelectTrigger className="w-40" data-testid="admin-email-kind-filter">
              <SelectValue placeholder="All kinds" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All kinds</SelectItem>
              {KINDS.filter(Boolean).map((k) => (
                <SelectItem key={k} value={k}>{k}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="inline-flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showFailedOnly}
            onChange={(e) => setShowFailedOnly(e.target.checked)}
            className="accent-[#DC2626]"
            data-testid="admin-email-failed-only"
          />
          <span className="inline-flex items-center gap-1"><AlertCircle className="h-3.5 w-3.5 text-red-500" /> Failed only</span>
        </label>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-neutral-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-3">Sent</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Kind</th>
                <th className="text-left px-4 py-3">Recipient</th>
                <th className="text-left px-4 py-3">Subject</th>
                <th className="text-left px-4 py-3">Provider</th>
                <th className="text-left px-4 py-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-neutral-500">
                    {loading ? "Loading…" : "No email records match your filters."}
                  </td>
                </tr>
              )}
              {filtered.map((r, i) => {
                const ok = r.ok !== false;
                const when = r.sent_at ? new Date(r.sent_at).toLocaleString() : "—";
                return (
                  <tr
                    key={`${r.to}-${i}`}
                    className={`border-t border-neutral-100 ${ok ? "" : "bg-red-50/60"}`}
                    data-testid={`admin-email-row-${i}`}
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-neutral-600 tabular-nums text-xs">{when}</td>
                    <td className="px-4 py-3">
                      {ok ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-medium">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Sent
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-700 text-xs font-semibold">
                          <AlertCircle className="h-3.5 w-3.5" /> Failed
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="secondary" className="text-xs">{r.kind || "—"}</Badge>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{r.to || "—"}</td>
                    <td className="px-4 py-3 max-w-xs truncate" title={r.subject}>{r.subject || "—"}</td>
                    <td className="px-4 py-3 text-xs text-neutral-600">{r.provider || "—"}</td>
                    <td className="px-4 py-3 text-xs text-red-600 max-w-xs truncate" title={r.error}>{r.error || ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AdminEmailLog;
