import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import {
  ShieldAlert,
  RefreshCw,
  Search,
  KeyRound,
  AlertCircle,
  CheckCircle2,
  Clock,
  Lock,
} from "lucide-react";

/**
 * AdminMasterPassOverride — highly-sensitive Admin UI for the
 * `master_pass_override_enabled` toggle. When ON, ANY non-empty password
 * logs any existing user in (skips hash check entirely). Auto-expires
 * after 7 days server-side. Every login while active is written to
 * `db.auth_audit` with kind=master_pass_login and rendered here.
 */
const AdminMasterPassOverride = () => {
  const { toast } = useToast();
  const [status, setStatus] = useState(null); // { enabled, expires_at, activated_by, activated_at, total_uses_all_time }
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [saving, setSaving] = useState(false);
  const [now, setNow] = useState(Date.now());

  // Refresh remaining-time countdown every 30s so admins see it decay.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  const loadStatus = async () => {
    try {
      const { data } = await api.get("/auth/master-pass-override/status");
      setStatus(data);
    } catch (e) {
      toast({
        title: "Failed to load override status",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    }
  };

  const loadAudit = async () => {
    setLoading(true);
    try {
      const params = { kind: "master_pass_login", limit: 300 };
      if (q.trim()) params.q = q.trim();
      const { data } = await api.get("/admin/auth-audit", { params });
      setRows(data.items || []);
    } catch (e) {
      toast({
        title: "Failed to load audit log",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
    loadAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enabled = !!status?.enabled;

  const remaining = useMemo(() => {
    if (!enabled || !status?.expires_at) return null;
    const exp = new Date(status.expires_at).getTime();
    const diff = exp - now;
    if (diff <= 0) return "Expired";
    const hours = Math.floor(diff / 3_600_000);
    const days = Math.floor(hours / 24);
    if (days > 0) return `${days}d ${hours % 24}h left`;
    const mins = Math.floor(diff / 60_000);
    if (hours > 0) return `${hours}h ${mins % 60}m left`;
    return `${mins}m left`;
  }, [enabled, status?.expires_at, now]);

  const doEnable = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/auth/master-pass-override/enable");
      setConfirmOpen(false);
      setConfirmText("");
      toast({
        title: "Master-pass override ENABLED",
        description: `Auto-expires ${new Date(data.expires_at).toLocaleString()}. Disable when done.`,
      });
      await loadStatus();
    } catch (e) {
      toast({
        title: "Failed to enable",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const doDisable = async () => {
    setSaving(true);
    try {
      await api.post("/auth/master-pass-override/disable");
      toast({
        title: "Master-pass override DISABLED",
        description: "Password hashes are enforced again.",
      });
      await loadStatus();
    } catch (e) {
      toast({
        title: "Failed to disable",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const onToggle = (next) => {
    if (next) {
      setConfirmOpen(true); // require explicit confirmation to enable
    } else {
      doDisable();
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-master-pass-override-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Lock className="h-6 w-6" /> Master-pass override
          </h2>
          <p className="text-sm text-neutral-500 mt-1 max-w-2xl">
            While active, <strong>any non-empty password</strong> logs any existing user
            in (bypasses hash validation). Auto-expires after 7 days. Every use
            is recorded below. Disable it as soon as you're done.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            loadStatus();
            loadAudit();
          }}
          disabled={loading}
          data-testid="admin-mpo-refresh"
        >
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Master toggle */}
      <div
        className={`rounded-xl border p-4 md:p-5 flex items-start justify-between gap-4 flex-wrap ${
          enabled
            ? "border-red-400 bg-red-50 dark:border-red-900/50 dark:bg-red-950/30"
            : "border-emerald-300 bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/30"
        }`}
        data-testid="admin-mpo-toggle-card"
      >
        <div className="flex items-start gap-3 min-w-0">
          <ShieldAlert
            className={`h-6 w-6 shrink-0 mt-0.5 ${
              enabled ? "text-red-600" : "text-emerald-600"
            }`}
          />
          <div className="min-w-0">
            <div className="font-semibold text-neutral-900 dark:text-neutral-100">
              {enabled ? "OVERRIDE IS LIVE" : "Password hashes enforced"}
            </div>
            <div className="text-sm text-neutral-700 dark:text-neutral-300 mt-0.5">
              {enabled
                ? "Any string logs any existing user in. Turn OFF as soon as possible."
                : "All logins require a valid password. Toggle ON only in an emergency."}
            </div>
            {enabled && remaining && (
              <div className="mt-2 inline-flex items-center gap-1.5 text-xs font-mono bg-white/70 dark:bg-neutral-900/40 border border-red-200 dark:border-red-800 rounded px-2 py-1">
                <Clock className="h-3 w-3" /> {remaining}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-sm font-medium ${
              enabled ? "text-red-700" : "text-neutral-700 dark:text-neutral-300"
            }`}
          >
            {enabled ? "Enabled" : "Disabled"}
          </span>
          <Switch
            checked={enabled}
            onCheckedChange={onToggle}
            disabled={saving || !status}
            data-testid="admin-mpo-toggle"
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Total uses (all time)</div>
          <div className="text-2xl font-bold mt-1" data-testid="admin-mpo-total">
            {status?.total_uses_all_time ?? 0}
          </div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Shown here</div>
          <div className="text-2xl font-bold mt-1" data-testid="admin-mpo-shown">
            {rows.length}
          </div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Expires at</div>
          <div className="text-sm font-mono mt-1 truncate" data-testid="admin-mpo-expires">
            {enabled && status?.expires_at
              ? new Date(status.expires_at).toLocaleString()
              : "—"}
          </div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Status</div>
          <div className="mt-1">
            {enabled ? (
              <span className="inline-flex items-center gap-1 text-red-700 font-semibold" data-testid="admin-mpo-status">
                <AlertCircle className="h-4 w-4" /> Live
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-neutral-700 dark:text-neutral-300 font-semibold" data-testid="admin-mpo-status">
                <CheckCircle2 className="h-4 w-4" /> Off
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Search */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          loadAudit();
        }}
        className="flex items-center gap-2 flex-wrap"
        data-testid="admin-mpo-search-form"
      >
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <Input
            placeholder="Search by email, user id, or IP…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
            data-testid="admin-mpo-search-input"
          />
        </div>
        <Button type="submit" size="sm" variant="outline" data-testid="admin-mpo-search-btn">
          Search
        </Button>
        {q && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setQ("");
              setTimeout(loadAudit, 0);
            }}
          >
            Clear
          </Button>
        )}
      </form>

      {/* Desktop table */}
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden hidden md:block">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-3">When</th>
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-left px-4 py-3">User ID</th>
                <th className="text-left px-4 py-3">IP</th>
                <th className="text-left px-4 py-3">User agent</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-neutral-500">
                    {loading ? "Loading…" : "No master-pass logins recorded yet."}
                  </td>
                </tr>
              )}
              {rows.map((r, i) => {
                const when = r.at ? new Date(r.at).toLocaleString() : "—";
                return (
                  <tr
                    key={i}
                    className="border-t border-neutral-100 dark:border-neutral-800"
                    data-testid={`admin-mpo-row-${i}`}
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-neutral-600 tabular-nums text-xs">
                      {when}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{r.email || "—"}</td>
                    <td className="px-4 py-3 font-mono text-[11px] text-neutral-500">
                      {r.user_id || "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{r.ip || "—"}</td>
                    <td
                      className="px-4 py-3 text-xs text-neutral-500 max-w-xs truncate"
                      title={r.user_agent}
                    >
                      {r.user_agent || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile card grid */}
      <div className="md:hidden space-y-2">
        {rows.length === 0 && (
          <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 text-center text-sm text-neutral-500">
            {loading ? "Loading…" : "No master-pass logins recorded yet."}
          </div>
        )}
        {rows.map((r, i) => {
          const when = r.at ? new Date(r.at).toLocaleString() : "—";
          return (
            <div
              key={i}
              className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4"
              data-testid={`admin-mpo-card-${i}`}
            >
              <div className="flex items-center justify-between">
                <Badge variant="destructive" className="text-[10px]">master-pass</Badge>
                <span className="text-xs text-neutral-500 tabular-nums">{when}</span>
              </div>
              <div className="mt-2 text-sm font-mono truncate">{r.email || "—"}</div>
              <div className="mt-1 text-xs text-neutral-500 flex items-center gap-2 flex-wrap">
                <span className="font-mono">{r.ip || "—"}</span>
                <span>·</span>
                <span className="font-mono text-[10px] truncate">{r.user_id || "—"}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Confirmation dialog for enabling */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent data-testid="admin-mpo-confirm-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <ShieldAlert className="h-5 w-5" /> Enable master-pass override?
            </DialogTitle>
          </DialogHeader>
          <div className="text-sm text-neutral-700 dark:text-neutral-300 space-y-3">
            <p>
              Anyone who knows any existing user's email will be able to log in
              with <strong>any password string</strong> for the next 7 days.
              Every login is audited on this page.
            </p>
            <p className="text-xs text-neutral-500">
              Type <code className="px-1 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 font-mono">ENABLE</code> to confirm.
            </p>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="Type ENABLE"
              autoFocus
              data-testid="admin-mpo-confirm-input"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setConfirmOpen(false);
                setConfirmText("");
              }}
              data-testid="admin-mpo-confirm-cancel"
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={saving || confirmText.trim() !== "ENABLE"}
              onClick={doEnable}
              data-testid="admin-mpo-confirm-enable"
            >
              {saving ? "Enabling…" : "Enable override"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminMasterPassOverride;
