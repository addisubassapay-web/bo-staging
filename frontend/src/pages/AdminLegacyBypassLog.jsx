import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import {
  ShieldAlert,
  RefreshCw,
  Search,
  KeyRound,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

/**
 * AdminLegacyBypassLog — audit UI for the "any password" legacy-account login
 * bypass. Shows every /api/auth/login bypass event (kind=legacy_bypass_login)
 * plus a master toggle that turns the whole bypass on/off globally.
 */
const AdminLegacyBypassLog = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [totalBypass, setTotalBypass] = useState(0);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [bypassEnabled, setBypassEnabled] = useState(true);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [savingToggle, setSavingToggle] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = { kind: "legacy_bypass_login", limit: 300 };
      if (q.trim()) params.q = q.trim();
      const { data } = await api.get("/admin/auth-audit", { params });
      setRows(data.items || []);
      setTotalBypass(data.total_bypass || 0);
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

  const loadSettings = async () => {
    try {
      const { data } = await api.get("/admin/settings");
      setBypassEnabled(data.legacy_bypass_enabled !== false);
    } catch (e) {
      // silent — settings load is best-effort
    } finally {
      setSettingsLoaded(true);
    }
  };

  useEffect(() => {
    load();
    loadSettings();
  }, []);

  const toggleBypass = async (next) => {
    setSavingToggle(true);
    try {
      await api.put("/admin/settings", { legacy_bypass_enabled: next });
      setBypassEnabled(next);
      toast({
        title: next ? "Bypass turned ON" : "Bypass turned OFF",
        description: next
          ? "Legacy users can log in with any password again."
          : "Legacy users must use their real password from now on.",
      });
    } catch (e) {
      toast({
        title: "Failed to update",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSavingToggle(false);
    }
  };

  const filtered = useMemo(() => rows, [rows]);

  const uniqueUsers = useMemo(
    () => new Set(rows.map((r) => r.user_id).filter(Boolean)).size,
    [rows],
  );

  return (
    <div className="space-y-6" data-testid="admin-legacy-bypass-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <KeyRound className="h-6 w-6" /> Legacy bypass audit
          </h2>
          <p className="text-sm text-neutral-500 mt-1 max-w-2xl">
            Every time a user flagged <code className="text-[11px] bg-neutral-100 dark:bg-neutral-800 px-1 rounded">must_change_password=true</code>{" "}
            logs in with any password (the legacy escape hatch), we record it
            here. The toggle below turns the whole bypass on or off globally.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={load}
          disabled={loading}
          data-testid="admin-bypass-refresh"
        >
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Master toggle */}
      <div
        className={`rounded-xl border p-4 md:p-5 flex items-start justify-between gap-4 flex-wrap ${
          bypassEnabled
            ? "border-amber-300 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/30"
            : "border-emerald-300 bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/30"
        }`}
        data-testid="admin-bypass-toggle-card"
      >
        <div className="flex items-start gap-3 min-w-0">
          <ShieldAlert
            className={`h-6 w-6 shrink-0 mt-0.5 ${
              bypassEnabled ? "text-amber-600" : "text-emerald-600"
            }`}
          />
          <div className="min-w-0">
            <div className="font-semibold text-neutral-900 dark:text-neutral-100">
              Legacy &ldquo;any password&rdquo; bypass
            </div>
            <div className="text-sm text-neutral-600 dark:text-neutral-300 mt-0.5">
              {bypassEnabled
                ? "ON — flagged legacy users can log in with any password (still forced to change on first login)."
                : "OFF — every user must use their real password. Turn ON temporarily to onboard the legacy fleet."}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {bypassEnabled ? "Enabled" : "Disabled"}
          </span>
          <Switch
            checked={bypassEnabled}
            onCheckedChange={toggleBypass}
            disabled={savingToggle || !settingsLoaded}
            data-testid="admin-bypass-toggle"
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Total bypass events</div>
          <div className="text-2xl font-bold mt-1" data-testid="admin-bypass-total">{totalBypass}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Unique users (shown)</div>
          <div className="text-2xl font-bold mt-1" data-testid="admin-bypass-unique">{uniqueUsers}</div>
        </div>
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Status</div>
          <div className="mt-1">
            {bypassEnabled ? (
              <span className="inline-flex items-center gap-1 text-amber-700 font-semibold">
                <AlertCircle className="h-4 w-4" /> Bypass live
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-neutral-700 dark:text-neutral-300 font-semibold">
                <CheckCircle2 className="h-4 w-4" /> Bypass disabled
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Search */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        className="flex items-center gap-2 flex-wrap"
        data-testid="admin-bypass-search-form"
      >
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <Input
            placeholder="Search by email, user id, or IP…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
            data-testid="admin-bypass-search-input"
          />
        </div>
        <Button type="submit" size="sm" variant="outline" data-testid="admin-bypass-search-btn">
          Search
        </Button>
        {q && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setQ("");
              setTimeout(load, 0);
            }}
          >
            Clear
          </Button>
        )}
      </form>

      {/* Desktop table (>=768px) */}
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
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-neutral-500">
                    {loading ? "Loading…" : "No bypass logins recorded yet."}
                  </td>
                </tr>
              )}
              {filtered.map((r, i) => {
                const when = r.at ? new Date(r.at).toLocaleString() : "—";
                return (
                  <tr
                    key={i}
                    className="border-t border-neutral-100 dark:border-neutral-800"
                    data-testid={`admin-bypass-row-${i}`}
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-neutral-600 tabular-nums text-xs">
                      {when}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{r.email || "—"}</td>
                    <td className="px-4 py-3 font-mono text-[11px] text-neutral-500">
                      {r.user_id || "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{r.ip || "—"}</td>
                    <td className="px-4 py-3 text-xs text-neutral-500 max-w-xs truncate" title={r.user_agent}>
                      {r.user_agent || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile card grid (<768px) */}
      <div className="md:hidden space-y-2">
        {filtered.length === 0 && (
          <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 text-center text-sm text-neutral-500">
            {loading ? "Loading…" : "No bypass logins recorded yet."}
          </div>
        )}
        {filtered.map((r, i) => {
          const when = r.at ? new Date(r.at).toLocaleString() : "—";
          return (
            <div
              key={i}
              className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4"
              data-testid={`admin-bypass-card-${i}`}
            >
              <div className="flex items-center justify-between">
                <Badge variant="secondary" className="text-[10px]">bypass</Badge>
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
    </div>
  );
};

export default AdminLegacyBypassLog;
