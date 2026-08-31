import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import {
  KeyRound,
  RefreshCw,
  Search,
  Mail,
  ShieldAlert,
  Lock,
  CheckCircle2,
  AlertCircle,
  Users as UsersIcon,
} from "lucide-react";

/**
 * AdminPasswordResets — one page to manage password resets for every
 * account in the database. Pulls `/admin/users`, offers search + filters
 * (locked, unverified email, must-change flag, missing hash, role), plus
 * bulk selection with two dispatch modes:
 *
 *  1) Set temp password  → POST /admin/users/bulk-password-reset {mode:"temp"}
 *  2) Send reset email   → POST /admin/users/bulk-password-reset {mode:"email"}
 *
 * Per-row single-user reset still uses the existing
 * POST /admin/users/{id}/reset-password endpoint.
 */
const PAGE_SIZE = 50;

const AdminPasswordResets = () => {
  const { toast } = useToast();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all"); // all|locked|unverified|must_change|no_hash|admin|user|seller
  const [selected, setSelected] = useState(() => new Set());
  const [page, setPage] = useState(1);

  // Dialogs
  const [singleTarget, setSingleTarget] = useState(null); // user obj
  const [singlePwd, setSinglePwd] = useState("");
  const [bulkMode, setBulkMode] = useState(null); // "temp" | "email" | null
  const [bulkTempPwd, setBulkTempPwd] = useState("Welcome-2026");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/users");
      setUsers(Array.isArray(data) ? data : []);
    } catch (e) {
      toast({
        title: "Failed to load accounts",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reset pagination when filter/search changes
  useEffect(() => {
    setPage(1);
    setSelected(new Set());
  }, [q, filter]);

  const isLocked = (u) =>
    u.locked_until ? new Date(u.locked_until).getTime() > Date.now() : false;

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return users.filter((u) => {
      if (needle) {
        const hay = `${u.email || ""} ${u.username || ""} ${u.id || ""}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      switch (filter) {
        case "locked":
          return isLocked(u);
        case "unverified":
          return !u.email_verified;
        case "must_change":
          return !!u.must_change_password;
        case "no_hash":
          // Backend strips password_hash from the payload — we can't tell
          // directly. Use `must_change_password` as a proxy, plus never
          // logged in.
          return !u.email_verified && !u.last_login_at;
        case "admin":
          return u.role === "admin";
        case "seller":
          return u.role === "seller" || u.seller_status === "approved";
        case "user":
          return u.role === "user";
        case "all":
        default:
          return true;
      }
    });
  }, [users, q, filter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = useMemo(
    () => filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filtered, page],
  );

  const allPageSelected =
    pageRows.length > 0 && pageRows.every((u) => selected.has(u.id));

  const togglePageAll = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pageRows.forEach((u) => next.delete(u.id));
      } else {
        pageRows.forEach((u) => next.add(u.id));
      }
      return next;
    });
  };

  const toggleOne = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllFiltered = () => {
    setSelected(new Set(filtered.map((u) => u.id)));
  };

  const clearSelection = () => setSelected(new Set());

  // ---- Single user reset ----
  const openSingle = (u) => {
    setSingleTarget(u);
    // Suggest a random 12-char password
    const pwd = Math.random().toString(36).slice(2, 8) + Math.random().toString(36).slice(2, 8);
    setSinglePwd(pwd);
  };

  const doSingleReset = async () => {
    if (!singleTarget) return;
    if ((singlePwd || "").length < 6) {
      toast({
        title: "Password too short",
        description: "Must be at least 6 characters.",
        variant: "destructive",
      });
      return;
    }
    setSaving(true);
    try {
      await api.post(`/admin/users/${singleTarget.id}/reset-password`, {
        new_password: singlePwd,
      });
      toast({
        title: `Password reset for ${singleTarget.username}`,
        description: `Share: ${singleTarget.email} · ${singlePwd}`,
      });
      setSingleTarget(null);
      setSinglePwd("");
      load();
    } catch (e) {
      toast({
        title: "Reset failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const sendSingleEmail = async (u) => {
    setSaving(true);
    try {
      const { data } = await api.post("/admin/users/bulk-password-reset", {
        mode: "email",
        user_ids: [u.id],
      });
      toast({
        title: `Reset email sent`,
        description: `${data.emailed || 0} sent · ${data.skipped || 0} skipped for ${u.email}`,
      });
    } catch (e) {
      toast({
        title: "Email dispatch failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  // ---- Bulk actions ----
  const openBulk = (mode) => {
    if (selected.size === 0) {
      toast({
        title: "Nothing selected",
        description: "Tick at least one account first.",
        variant: "destructive",
      });
      return;
    }
    setBulkMode(mode);
  };

  const runBulk = async () => {
    if (!bulkMode) return;
    if (bulkMode === "temp" && bulkTempPwd.length < 6) {
      toast({
        title: "Temp password too short",
        description: "Must be at least 6 characters.",
        variant: "destructive",
      });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        mode: bulkMode,
        user_ids: Array.from(selected),
      };
      if (bulkMode === "temp") payload.temp_password = bulkTempPwd;
      const { data } = await api.post("/admin/users/bulk-password-reset", payload);
      if (bulkMode === "temp") {
        toast({
          title: `Bulk temp reset done`,
          description: `${data.affected} accounts · temp password: ${data.temp_password}`,
        });
      } else {
        toast({
          title: `Bulk reset emails dispatched`,
          description: `${data.emailed || 0} emailed · ${data.skipped || 0} skipped`,
        });
      }
      setBulkMode(null);
      clearSelection();
      load();
    } catch (e) {
      toast({
        title: "Bulk operation failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  // ---- Stats ----
  const stats = useMemo(() => {
    return {
      total: users.length,
      locked: users.filter(isLocked).length,
      unverified: users.filter((u) => !u.email_verified).length,
      mustChange: users.filter((u) => u.must_change_password).length,
      admins: users.filter((u) => u.role === "admin").length,
    };
  }, [users]);

  return (
    <div className="space-y-6" data-testid="admin-password-resets-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <KeyRound className="h-6 w-6" /> Password resets
          </h2>
          <p className="text-sm text-neutral-500 mt-1 max-w-2xl">
            Every account in the database is listed here. Search, filter,
            select accounts, and either <strong>set a shared temp password</strong>{" "}
            or <strong>dispatch reset emails</strong> in bulk. Per-row reset
            still works too.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={load}
          disabled={loading}
          data-testid="admin-pwd-refresh"
        >
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Total accounts" value={stats.total} testid="pwd-stat-total" icon={UsersIcon} />
        <StatCard label="Locked out" value={stats.locked} testid="pwd-stat-locked" tone={stats.locked ? "red" : "neutral"} icon={Lock} />
        <StatCard label="Email unverified" value={stats.unverified} testid="pwd-stat-unverified" tone="amber" icon={AlertCircle} />
        <StatCard label="Must change pwd" value={stats.mustChange} testid="pwd-stat-mustchange" tone="amber" icon={ShieldAlert} />
        <StatCard label="Admins" value={stats.admins} testid="pwd-stat-admins" icon={CheckCircle2} />
      </div>

      {/* Controls */}
      <div className="flex flex-col md:flex-row md:items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <Input
            placeholder="Search email, username, or user id…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
            data-testid="admin-pwd-search"
          />
        </div>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-full md:w-52" data-testid="admin-pwd-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All accounts</SelectItem>
            <SelectItem value="locked">Locked out</SelectItem>
            <SelectItem value="unverified">Email unverified</SelectItem>
            <SelectItem value="must_change">Must change pwd</SelectItem>
            <SelectItem value="no_hash">Never logged in</SelectItem>
            <SelectItem value="admin">Admins</SelectItem>
            <SelectItem value="seller">Sellers</SelectItem>
            <SelectItem value="user">Regular users</SelectItem>
          </SelectContent>
        </Select>
        <div className="text-sm text-neutral-500" data-testid="admin-pwd-count">
          {filtered.length} match{filtered.length === 1 ? "" : "es"}
          {selected.size > 0 && (
            <>
              {" · "}
              <span className="font-semibold text-neutral-900 dark:text-neutral-100">
                {selected.size} selected
              </span>
            </>
          )}
        </div>
      </div>

      {/* Bulk toolbar */}
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/50 p-3 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mr-1">
          Bulk actions
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={selectAllFiltered}
          disabled={filtered.length === 0}
          data-testid="admin-pwd-select-all"
        >
          Select all filtered ({filtered.length})
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={clearSelection}
          disabled={selected.size === 0}
          data-testid="admin-pwd-clear-selection"
        >
          Clear
        </Button>
        <div className="flex-1" />
        <Button
          size="sm"
          variant="outline"
          onClick={() => openBulk("email")}
          disabled={selected.size === 0}
          className="border-blue-300 text-blue-700 hover:bg-blue-50"
          data-testid="admin-pwd-bulk-email"
        >
          <Mail className="h-4 w-4 mr-1.5" /> Send reset emails ({selected.size})
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => openBulk("temp")}
          disabled={selected.size === 0}
          className="border-amber-300 text-amber-700 hover:bg-amber-50"
          data-testid="admin-pwd-bulk-temp"
        >
          <KeyRound className="h-4 w-4 mr-1.5" /> Set temp password ({selected.size})
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-3 py-3 w-10">
                  <Checkbox
                    checked={allPageSelected}
                    onCheckedChange={togglePageAll}
                    data-testid="admin-pwd-select-page"
                  />
                </th>
                <th className="text-left px-3 py-3">Account</th>
                <th className="text-left px-3 py-3">Role</th>
                <th className="text-left px-3 py-3">Status</th>
                <th className="text-left px-3 py-3">Password flags</th>
                <th className="text-left px-3 py-3">Created</th>
                <th className="text-right px-3 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-neutral-500">
                    {loading ? "Loading accounts…" : "No accounts match this filter."}
                  </td>
                </tr>
              )}
              {pageRows.map((u) => {
                const locked = isLocked(u);
                return (
                  <tr
                    key={u.id}
                    className="border-t border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50/60 dark:hover:bg-neutral-900/40"
                    data-testid={`admin-pwd-row-${u.id}`}
                  >
                    <td className="px-3 py-3">
                      <Checkbox
                        checked={selected.has(u.id)}
                        onCheckedChange={() => toggleOne(u.id)}
                        data-testid={`admin-pwd-select-${u.id}`}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-medium truncate max-w-[220px]">{u.username || "—"}</div>
                      <div className="text-xs text-neutral-500 font-mono truncate max-w-[240px]">{u.email}</div>
                    </td>
                    <td className="px-3 py-3">
                      <Badge
                        variant={u.role === "admin" ? "destructive" : "secondary"}
                        className="text-[10px]"
                      >
                        {u.role || "user"}
                      </Badge>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1">
                        {!u.is_active && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-200 text-neutral-700">
                            disabled
                          </span>
                        )}
                        {locked && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700">
                            locked
                          </span>
                        )}
                        {u.email_verified ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                            verified
                          </span>
                        ) : (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
                            unverified
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1">
                        {u.must_change_password && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                            must_change
                          </span>
                        )}
                        {u.failed_login_attempts > 0 && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-700">
                            {u.failed_login_attempts} failed
                          </span>
                        )}
                        {!u.must_change_password && u.failed_login_attempts === 0 && (
                          <span className="text-[10px] text-neutral-400">clean</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-neutral-500 tabular-nums whitespace-nowrap">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex justify-end gap-1 flex-wrap">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => sendSingleEmail(u)}
                          disabled={saving}
                          className="h-8 px-2 text-xs text-blue-700 hover:bg-blue-50"
                          title="Send /reset-password link to this email"
                          data-testid={`admin-pwd-send-email-${u.id}`}
                        >
                          <Mail className="h-3.5 w-3.5 mr-1" /> Email
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => openSingle(u)}
                          className="h-8 px-2 text-xs text-neutral-600 hover:text-red-700"
                          data-testid={`admin-pwd-set-temp-${u.id}`}
                        >
                          <KeyRound className="h-3.5 w-3.5 mr-1" /> Set pwd
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-neutral-100 dark:border-neutral-800 px-4 py-2 text-sm">
            <div className="text-xs text-neutral-500">
              Page {page} of {totalPages} · showing {(page - 1) * PAGE_SIZE + 1}–
              {Math.min(page * PAGE_SIZE, filtered.length)}
            </div>
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="ghost"
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                data-testid="admin-pwd-prev"
              >
                Prev
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={page === totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                data-testid="admin-pwd-next"
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Single-user set-password dialog */}
      <Dialog open={!!singleTarget} onOpenChange={(o) => !o && setSingleTarget(null)}>
        <DialogContent data-testid="admin-pwd-single-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5" /> Set password for {singleTarget?.username}
            </DialogTitle>
          </DialogHeader>
          <div className="text-sm space-y-3">
            <div className="text-neutral-600">
              User <span className="font-mono">{singleTarget?.email}</span> will be
              forced to change this password on their next login.
            </div>
            <Input
              value={singlePwd}
              onChange={(e) => setSinglePwd(e.target.value)}
              placeholder="New password (min 6 chars)"
              data-testid="admin-pwd-single-input"
              autoFocus
            />
            <div className="text-xs text-neutral-500">
              Tip: share this credential over a secure channel — the user won't
              receive an email.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSingleTarget(null)}>
              Cancel
            </Button>
            <Button
              disabled={saving || singlePwd.length < 6}
              onClick={doSingleReset}
              data-testid="admin-pwd-single-confirm"
            >
              {saving ? "Setting…" : "Set password"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk dialog */}
      <Dialog open={!!bulkMode} onOpenChange={(o) => !o && setBulkMode(null)}>
        <DialogContent data-testid="admin-pwd-bulk-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {bulkMode === "email" ? (
                <>
                  <Mail className="h-5 w-5 text-blue-600" /> Send reset emails to{" "}
                  {selected.size} account{selected.size === 1 ? "" : "s"}?
                </>
              ) : (
                <>
                  <ShieldAlert className="h-5 w-5 text-amber-600" /> Set shared temp
                  password for {selected.size} account{selected.size === 1 ? "" : "s"}?
                </>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="text-sm space-y-3">
            {bulkMode === "email" ? (
              <p className="text-neutral-600">
                Each selected user will receive a one-time reset link that
                expires in 24 hours. Delivery goes through the live Hostinger
                SMTP mailer. Failures are counted but don't stop the batch.
              </p>
            ) : (
              <>
                <p className="text-neutral-600">
                  Every selected account's password will be overwritten with the
                  same temporary value and flagged{" "}
                  <code className="text-xs px-1 bg-neutral-100 rounded">
                    must_change_password
                  </code>
                  . Users can log in immediately and are forced to pick a new
                  password.
                </p>
                <Input
                  value={bulkTempPwd}
                  onChange={(e) => setBulkTempPwd(e.target.value)}
                  placeholder="Temp password (min 6 chars)"
                  data-testid="admin-pwd-bulk-temp-input"
                />
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkMode(null)}>
              Cancel
            </Button>
            <Button
              onClick={runBulk}
              disabled={
                saving || (bulkMode === "temp" && bulkTempPwd.length < 6)
              }
              variant={bulkMode === "temp" ? "destructive" : "default"}
              data-testid="admin-pwd-bulk-confirm"
            >
              {saving
                ? "Working…"
                : bulkMode === "email"
                ? "Dispatch emails"
                : "Set temp password"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const StatCard = ({ label, value, testid, tone = "neutral", icon: Icon }) => {
  const toneMap = {
    neutral: "text-neutral-600",
    red: "text-red-600",
    amber: "text-amber-600",
    emerald: "text-emerald-600",
  };
  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
      <div className="flex items-center gap-1.5 text-xs text-neutral-500 uppercase tracking-wider">
        {Icon && <Icon className="h-3.5 w-3.5" />} {label}
      </div>
      <div
        className={`text-2xl font-bold mt-1 tabular-nums ${toneMap[tone] || toneMap.neutral}`}
        data-testid={testid}
      >
        {value}
      </div>
    </div>
  );
};

export default AdminPasswordResets;
