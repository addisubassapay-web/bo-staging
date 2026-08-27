import React, { useEffect, useState } from "react";
import { NavLink, Route, Routes, Navigate, useNavigate, useLocation } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { LayoutDashboard, Users, Package, ShoppingBag, FolderTree, Trash2, Star, Plus, Settings as SettingsIcon, Wallet, Store as StoreIcon, Save, Check, X as XIcon, Database, IdCard, LayoutGrid, GripVertical, AlertCircle, ShieldAlert, CheckCircle2, XCircle, Clock, MessageCircle, ChevronDown, ChevronUp, Bitcoin, CheckSquare, Square as SquareIcon, Ticket, Mail, Zap, Menu } from "lucide-react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import AdminShelves from "@/pages/AdminShelves";
import ApifySync from "@/pages/AdminApifySync";
import ApifySyncTicker from "@/components/ApifySyncTicker";
import R2StorageTicker from "@/components/R2StorageTicker";
import PickupTimingTuner from "@/components/PickupTimingTuner";
import SuspendedSellersCard from "@/components/SuspendedSellersCard";
import AdminPaymentMethods from "@/pages/AdminPaymentMethods";
import AdminLedgerAudit from "@/pages/AdminLedgerAudit";
import AdminEmailLog from "@/pages/AdminEmailLog";
import AdminStoreBoosts from "@/pages/AdminStoreBoosts";
import AdminSupport from "@/pages/AdminSupport";
import AdminProducts from "@/pages/AdminProducts";
import AdminSearchInsights from "@/pages/AdminSearchInsights";
import AdminPaymentReviews from "@/pages/AdminPaymentReviews";

const SidebarLink = ({ to, icon: Icon, children }) => (
  <NavLink
    to={to}
    end
    className={({ isActive }) =>
      `flex items-center gap-2 px-3 py-2 rounded-md text-sm ${isActive ? "bg-[#FFF3F2] text-[#FF211F] font-medium" : "text-neutral-700 hover:bg-neutral-100"}`
    }
  >
    <Icon className="h-4 w-4" /> {children}
  </NavLink>
);

const SidebarSupportLink = () => {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const { data } = await api.get("/admin/support/unread-count");
        if (alive) setUnread(data.unread || 0);
      } catch { /* silent */ }
    };
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return (
    <NavLink
      to="/admin/support-tickets"
      end
      className={({ isActive }) =>
        `flex items-center gap-2 px-3 py-2 rounded-md text-sm ${isActive ? "bg-[#FFF3F2] text-[#FF211F] font-medium" : "text-neutral-700 hover:bg-neutral-100"}`
      }
      data-testid="admin-sidebar-support"
    >
      <MessageCircle className="h-4 w-4" />
      <span className="flex-1">Support</span>
      {unread > 0 && (
        <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-emerald-500 text-white text-[10px] font-bold grid place-items-center tabular-nums" data-testid="admin-sidebar-support-badge">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </NavLink>
  );
};

const StatCard = ({ label, value, hint }) => (
  <div className="bg-white border border-neutral-200 rounded-lg p-5">
    <div className="text-sm text-neutral-500">{label}</div>
    <div className="text-2xl font-bold mt-1">{value}</div>
    {hint && <div className="text-xs text-neutral-400 mt-1">{hint}</div>}
  </div>
);

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  useEffect(() => { api.get("/admin/stats").then((r) => setStats(r.data)); }, []);
  if (!stats) return <div>Loading…</div>;
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      <ApifySyncTicker />
      <R2StorageTicker />
      <PickupTimingTuner />
      <SuspendedSellersCard />
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard label="Users" value={stats.users} />
        <StatCard label="Stores" value={stats.stores} />
        <StatCard label="Active listings" value={stats.active_listings} />
        <StatCard label="Sold listings" value={stats.sold_listings} />
        <StatCard label="Orders" value={stats.orders} />
        <StatCard label="Categories" value={stats.categories} />
        <StatCard label="Affiliate links" value={stats.affiliate_links} />
        <StatCard label="Pending withdrawals" value={stats.pending_withdrawals} hint={stats.pending_withdrawals > 0 ? "Requires review" : ""} />
        <StatCard label="Total revenue" value={formatPrice(stats.revenue)} hint={`Platform fees: ${formatPrice(stats.platform_fees)}`} />
      </div>
    </div>
  );
};

const WalletAdjustDialog = ({ user, onClose, onDone }) => {
  const { toast } = useToast();
  const [amount, setAmount] = useState("");
  const [direction, setDirection] = useState("credit"); // credit | debit
  const [bucket, setBucket] = useState("available"); // available | frozen
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const raw = parseFloat(amount);
    if (!Number.isFinite(raw) || raw <= 0) {
      toast({ title: "Enter a valid amount", variant: "destructive" }); return;
    }
    if (!description.trim()) {
      toast({ title: "Add a reason for the audit log", variant: "destructive" }); return;
    }
    const delta = direction === "debit" ? -raw : raw;
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/users/${user.id}/wallet-adjust`, {
        delta,
        description: description.trim(),
        bucket,
      });
      toast({
        title: `Wallet ${direction === "debit" ? "debited" : "credited"} ${raw.toFixed(2)}`,
        description: `New ${bucket} balance: $${(bucket === "frozen" ? data.wallet_frozen_balance : data.wallet_balance).toFixed(2)}`,
      });
      onDone?.(data);
      onClose();
    } catch (e) {
      toast({
        title: "Adjustment failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md" data-testid="wallet-adjust-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="h-5 w-5 text-[#FF211F]" /> Adjust wallet — {user.username}
          </DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3">
            <div className="text-xs text-neutral-500">Available</div>
            <div className="text-lg font-bold tabular-nums">${Number(user.wallet_balance || 0).toFixed(2)}</div>
          </div>
          <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3">
            <div className="text-xs text-neutral-500">Frozen</div>
            <div className="text-lg font-bold tabular-nums">${Number(user.wallet_frozen_balance || 0).toFixed(2)}</div>
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <Label>Direction</Label>
            <div className="flex gap-2 mt-1">
              <button
                type="button"
                onClick={() => setDirection("credit")}
                className={`flex-1 min-h-[44px] rounded-lg border text-sm font-semibold transition ${direction === "credit" ? "bg-emerald-600 text-white border-transparent" : "bg-white text-neutral-700 border-neutral-200 hover:border-emerald-400"}`}
                data-testid="wallet-adjust-credit-btn"
              >+ Credit</button>
              <button
                type="button"
                onClick={() => setDirection("debit")}
                className={`flex-1 min-h-[44px] rounded-lg border text-sm font-semibold transition ${direction === "debit" ? "bg-red-600 text-white border-transparent" : "bg-white text-neutral-700 border-neutral-200 hover:border-red-400"}`}
                data-testid="wallet-adjust-debit-btn"
              >− Debit</button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Amount (USD)</Label>
              <Input
                type="number" min="0.01" step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                className="mt-1"
                data-testid="wallet-adjust-amount"
              />
            </div>
            <div>
              <Label>Bucket</Label>
              <Select value={bucket} onValueChange={setBucket}>
                <SelectTrigger className="mt-1" data-testid="wallet-adjust-bucket"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="available">Available</SelectItem>
                  <SelectItem value="frozen">Frozen (escrow)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Reason (required — appears on the user&apos;s ledger)</Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Manual top-up for support ticket #123"
              className="mt-1"
              maxLength={300}
              data-testid="wallet-adjust-reason"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={submit}
            disabled={busy}
            className={direction === "debit" ? "bg-red-600 hover:bg-red-700 text-white" : "bg-emerald-600 hover:bg-emerald-700 text-white"}
            data-testid="wallet-adjust-submit"
          >
            {busy ? "Posting…" : (direction === "debit" ? "Debit wallet" : "Credit wallet")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const UsersMgr = () => {
  const [users, setUsers] = useState([]);
  const [lockedOnly, setLockedOnly] = useState(false);
  const [walletTarget, setWalletTarget] = useState(null);
  const { toast } = useToast();
  const load = () => api.get("/admin/users").then((r) => setUsers(r.data));
  useEffect(() => { load(); }, []);

  const toggleActive = async (u) => {
    await api.put(`/admin/users/${u.id}`, { is_active: !u.is_active });
    toast({ title: `User ${u.is_active ? "disabled" : "enabled"}` });
    load();
  };
  const setRole = async (u, role) => {
    await api.put(`/admin/users/${u.id}`, { role });
    load();
  };
  const del = async (u) => {
    if (!window.confirm(`Delete user ${u.username}? This removes their listings too.`)) return;
    await api.delete(`/admin/users/${u.id}`);
    toast({ title: "User deleted" });
    load();
  };
  const saveCap = async (u, value) => {
    const payload = value === "" || value === null ? { resell_markup_override: null } : { resell_markup_override: Number(value) };
    try {
      await api.put(`/admin/users/${u.id}`, payload);
      toast({ title: value === "" ? "Cap cleared" : `Resell cap set to ${value}%`, description: value === "" ? "Reverted to tier-based cap." : "Overrides the badge tier." });
      load();
    } catch (e) {
      toast({ title: "Update failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };

  const unlock = async (u) => {
    try {
      await api.post(`/admin/users/${u.id}/unlock`);
      toast({ title: `${u.username} unlocked`, description: "Failed-attempt counter reset. They can sign in again." });
      load();
    } catch (e) {
      toast({ title: "Unlock failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };
  const resetPassword = async (u) => {
    const pwd = window.prompt(
      `Set a new password for ${u.username} (${u.email}).\n\nMinimum 6 characters. The user can log in with this password immediately, then change it in their profile.`,
      ""
    );
    if (pwd === null) return; // cancelled
    if (pwd.length < 6) {
      toast({ title: "Password too short", description: "Must be at least 6 characters.", variant: "destructive" });
      return;
    }
    try {
      await api.post(`/admin/users/${u.id}/reset-password`, { new_password: pwd });
      // Show the new password back so the admin can hand it off. We
      // intentionally use a plain alert so the value isn't lost to a fade.
      window.alert(`Password reset. Share these credentials with ${u.username}:\n\nEmail: ${u.email}\nPassword: ${pwd}`);
      toast({ title: `Password reset for ${u.username}` });
      load();
    } catch (e) {
      toast({ title: "Reset failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };
  const bulkResetLegacy = async () => {
    const temp = window.prompt(
      "BULK RESET — every non-admin account will get this temporary password and be forced to change it on their next login.\n\nType a temp password (min 6 chars):",
      "Welcome-2026"
    );
    if (temp === null) return;
    if (temp.length < 6) {
      toast({ title: "Password too short", description: "Must be at least 6 characters.", variant: "destructive" });
      return;
    }
    if (!window.confirm(`This will overwrite the password on EVERY non-admin account (~${users.length - 1} users). Continue?`)) return;
    try {
      const { data } = await api.post("/admin/users/bulk-password-reset", {
        mode: "temp",
        all_non_admin: true,
        temp_password: temp,
      });
      window.alert(
        `Bulk reset complete.\n\n` +
        `Accounts updated: ${data.affected}\n` +
        `Temporary password: ${data.temp_password}\n\n` +
        `Share this with your users — they will be forced to pick a new password on their next login.`
      );
      toast({ title: `Bulk reset done`, description: `${data.affected} accounts now use the temp password.` });
      load();
    } catch (e) {
      toast({ title: "Bulk reset failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };
  const isLocked = (u) => {
    if (!u.locked_until) return false;
    return new Date(u.locked_until).getTime() > Date.now();
  };
  const lockSecondsLeft = (u) => {
    if (!u.locked_until) return 0;
    return Math.max(0, Math.floor((new Date(u.locked_until).getTime() - Date.now()) / 1000));
  };

  return (
    <div>
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <h2 className="text-2xl font-bold">Users</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setLockedOnly(false)}
            className={`h-8 px-3 rounded-full text-xs font-semibold transition border ${!lockedOnly ? "bg-neutral-900 text-white border-transparent" : "bg-white text-neutral-700 border-neutral-200 hover:border-[#2563EB] hover:text-[#2563EB]"}`}
            data-testid="users-filter-all"
          >All users ({users.length})</button>
          <button
            type="button"
            onClick={() => setLockedOnly(true)}
            className={`h-8 px-3 rounded-full text-xs font-semibold transition border inline-flex items-center gap-1 ${lockedOnly ? "bg-red-600 text-white border-transparent" : "bg-white text-red-700 border-red-200 hover:bg-red-50"}`}
            data-testid="users-filter-locked"
          >🔒 Locked only ({users.filter(isLocked).length})</button>
          <button
            type="button"
            onClick={bulkResetLegacy}
            className="h-8 px-3 rounded-full text-xs font-semibold transition border bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-900/40"
            title="Reset every non-admin account to a shared temporary password and force each user to pick a new one on their next login."
            data-testid="users-bulk-reset-btn"
          >Bulk reset (legacy)</button>
        </div>
      </div>
      <div className="bg-white border border-neutral-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-3">User</th>
              <th className="p-3">Email</th>
              <th className="p-3">Role</th>
              <th className="p-3">Sales</th>
              <th className="p-3" title="Personal markup cap that overrides the badge tier">Resell cap %</th>
              <th className="p-3">Wallet</th>
              <th className="p-3">Status</th>
              <th className="p-3">Login lock</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {(lockedOnly ? users.filter(isLocked) : users).map((u) => (
              <tr key={u.id} className="border-t border-neutral-100" data-testid={`admin-user-${u.id}`}>
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <div className="h-8 w-8 rounded-full bg-neutral-200 grid place-items-center text-xs font-semibold">{u.username[0].toUpperCase()}</div>
                    <span className="font-medium">{u.username}</span>
                  </div>
                </td>
                <td className="p-3 text-neutral-600">{u.email}</td>
                <td className="p-3">
                  <Select value={u.role} onValueChange={(v) => setRole(u, v)}>
                    <SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">User</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </td>
                <td className="p-3">{u.sales_count}</td>
                <td className="p-3">
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={0}
                      max={500}
                      defaultValue={u.resell_markup_override ?? ""}
                      onBlur={(e) => {
                        const raw = e.target.value.trim();
                        const cur = u.resell_markup_override;
                        if (raw === "" && cur == null) return;
                        if (raw !== "" && Number(raw) === Number(cur)) return;
                        saveCap(u, raw);
                      }}
                      placeholder="tier"
                      className="h-8 w-20 tabular-nums"
                      data-testid={`resell-cap-input-${u.id}`}
                    />
                    <span className="text-xs text-neutral-400">%</span>
                  </div>
                </td>
                <td className="p-3">
                  <div className="flex flex-col gap-1">
                    <div className="text-sm font-semibold tabular-nums" data-testid={`user-wallet-available-${u.id}`}>
                      ${Number(u.wallet_balance || 0).toFixed(2)}
                    </div>
                    {Number(u.wallet_frozen_balance || 0) > 0 && (
                      <div className="text-[11px] text-amber-700 tabular-nums" data-testid={`user-wallet-frozen-${u.id}`}>
                        + ${Number(u.wallet_frozen_balance || 0).toFixed(2)} frozen
                      </div>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setWalletTarget(u)}
                      className="h-7 px-2 text-xs border-emerald-300 text-emerald-700 hover:bg-emerald-50 mt-0.5 w-fit"
                      data-testid={`user-wallet-adjust-${u.id}`}
                    >
                      <Wallet className="h-3 w-3 mr-1" /> Adjust
                    </Button>
                  </div>
                </td>
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <Switch checked={u.is_active} onCheckedChange={() => toggleActive(u)} />
                    <span className="text-xs text-neutral-500">{u.is_active ? "Active" : "Disabled"}</span>
                  </div>
                </td>
                <td className="p-3">
                  {isLocked(u) ? (
                    <div className="flex items-center gap-2" data-testid={`user-lock-cell-${u.id}`}>
                      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 text-[11px] font-semibold">
                        🔒 Locked · {lockSecondsLeft(u)}s
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => unlock(u)}
                        className="h-7 px-2 text-xs border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                        data-testid={`user-unlock-btn-${u.id}`}
                      >Unlock</Button>
                    </div>
                  ) : u.failed_login_attempts > 0 ? (
                    <div className="flex items-center gap-2" data-testid={`user-lock-cell-${u.id}`}>
                      <span className="text-xs text-amber-600 font-semibold">{u.failed_login_attempts} failed</span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => unlock(u)}
                        className="h-7 px-2 text-xs text-neutral-500 hover:text-emerald-700"
                        title="Reset failed-login counter"
                        data-testid={`user-unlock-btn-${u.id}`}
                      >Reset</Button>
                    </div>
                  ) : (
                    <span className="text-xs text-neutral-400">—</span>
                  )}
                </td>
                <td className="p-3 text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => resetPassword(u)}
                      title="Set a new password for this user"
                      className="h-8 px-2 text-xs text-neutral-500 hover:text-[#2563EB]"
                      data-testid={`user-reset-pwd-btn-${u.id}`}
                    >
                      Reset password
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => del(u)} data-testid={`user-delete-btn-${u.id}`}><Trash2 className="h-4 w-4 text-neutral-500" /></Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-neutral-500 mt-2">
        Leave the resell cap empty to use the seller&apos;s badge tier. Enter a number (0–500) to hard-cap that user&apos;s maximum markup %.
      </p>
      {walletTarget && (
        <WalletAdjustDialog
          user={walletTarget}
          onClose={() => setWalletTarget(null)}
          onDone={() => load()}
        />
      )}
    </div>
  );
};

const ListingsMgr = () => {
  const [listings, setListings] = useState([]);
  const [filter, setFilter] = useState("");
  const { toast } = useToast();
  const load = () => {
    const params = filter ? { status_filter: filter } : {};
    api.get("/admin/listings", { params }).then((r) => setListings(r.data));
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleFeatured = async (l) => {
    await api.put(`/listings/${l.id}`, { featured: !l.featured });
    load();
  };
  const setStatus = async (l, status) => {
    await api.put(`/listings/${l.id}`, { status });
    load();
  };
  const del = async (l) => {
    if (!window.confirm("Delete this listing?")) return;
    await api.delete(`/listings/${l.id}`);
    toast({ title: "Deleted" });
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Listings</h2>
        <Select value={filter || "all"} onValueChange={(v) => setFilter(v === "all" ? "" : v)}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="sold">Sold</SelectItem>
            <SelectItem value="removed">Removed</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="bg-white border border-neutral-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-3">Item</th>
              <th className="p-3">Seller</th>
              <th className="p-3">Price</th>
              <th className="p-3">Status</th>
              <th className="p-3">Featured</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {listings.map((l) => (
              <tr key={l.id} className="border-t border-neutral-100">
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <img src={l.images?.[0]} alt="" className="h-10 w-10 rounded object-cover" />
                    <div className="max-w-xs">
                      <div className="font-medium line-clamp-1">{l.title}</div>
                      <div className="text-xs text-neutral-500">{l.category_name}</div>
                    </div>
                  </div>
                </td>
                <td className="p-3">{l.seller_name}</td>
                <td className="p-3 font-medium">{formatPrice(l.price)}</td>
                <td className="p-3">
                  <Select value={l.status} onValueChange={(v) => setStatus(l, v)}>
                    <SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="sold">Sold</SelectItem>
                      <SelectItem value="reserved">Reserved</SelectItem>
                      <SelectItem value="removed">Removed</SelectItem>
                    </SelectContent>
                  </Select>
                </td>
                <td className="p-3">
                  <button onClick={() => toggleFeatured(l)}>
                    <Star className={`h-4 w-4 ${l.featured ? "fill-yellow-400 text-yellow-400" : "text-neutral-300"}`} />
                  </button>
                </td>
                <td className="p-3 text-right">
                  <Button variant="ghost" size="sm" onClick={() => del(l)}><Trash2 className="h-4 w-4 text-neutral-500" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const OrdersMgr = () => {
  const [orders, setOrders] = useState([]);
  useEffect(() => { api.get("/admin/orders").then((r) => setOrders(r.data)); }, []);
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Orders</h2>
      <div className="bg-white border border-neutral-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-3">Order</th>
              <th className="p-3">Item</th>
              <th className="p-3">Buyer</th>
              <th className="p-3">Seller</th>
              <th className="p-3">Amount</th>
              <th className="p-3">Status</th>
              <th className="p-3">Date</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id} className="border-t border-neutral-100">
                <td className="p-3 font-mono text-xs">#{o.id.slice(0, 8)}</td>
                <td className="p-3 max-w-xs"><div className="line-clamp-1">{o.listing_title}</div></td>
                <td className="p-3">{o.buyer_name}</td>
                <td className="p-3">{o.seller_name}</td>
                <td className="p-3 font-medium">{formatPrice(o.amount + o.shipping_fee)}</td>
                <td className="p-3"><Badge variant="secondary" className="capitalize">{o.status}</Badge></td>
                <td className="p-3 text-neutral-500 text-xs">{new Date(o.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const CategoriesMgr = () => {
  const [cats, setCats] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", icon: "package", order: 0 });
  const { toast } = useToast();

  const load = () => api.get("/categories").then((r) => setCats(r.data));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name || !form.slug) return;
    await api.post("/categories", form);
    toast({ title: "Category created" });
    setOpen(false);
    setForm({ name: "", slug: "", icon: "package", order: 0 });
    load();
  };
  const del = async (id) => {
    if (!window.confirm("Delete this category?")) return;
    await api.delete(`/categories/${id}`);
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Categories</h2>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="bg-[#FF211F] hover:bg-[#e01d1b]"><Plus className="h-4 w-4 mr-1" /> New</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>New category</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div><Label>Slug</Label><Input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="e.g. jewelry" /></div>
              <div><Label>Icon (lucide name)</Label><Input value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} placeholder="package" /></div>
              <div><Label>Order</Label><Input type="number" value={form.order} onChange={(e) => setForm({ ...form, order: Number(e.target.value) })} /></div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button className="bg-[#FF211F] hover:bg-[#e01d1b]" onClick={create}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      <div className="bg-white border border-neutral-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-3">Name</th>
              <th className="p-3">Slug</th>
              <th className="p-3">Icon</th>
              <th className="p-3">Order</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {cats.map((c) => (
              <tr key={c.id} className="border-t border-neutral-100">
                <td className="p-3 font-medium">{c.name}</td>
                <td className="p-3 text-neutral-600">{c.slug}</td>
                <td className="p-3 text-neutral-600">{c.icon}</td>
                <td className="p-3">{c.order}</td>
                <td className="p-3 text-right">
                  <Button variant="ghost" size="sm" onClick={() => del(c.id)}><Trash2 className="h-4 w-4 text-neutral-500" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const SettingsMgr = () => {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  useEffect(() => { api.get("/admin/settings").then((r) => setSettings(r.data)); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/admin/settings", settings);
      setSettings(data);
      toast({ title: "Settings saved" });
    } catch {
      toast({ title: "Save failed", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const set = (k, v) => setSettings((s) => ({ ...s, [k]: v }));

  if (!settings) return <div>Loading…</div>;

  const modeField = (label, key) => (
    <div>
      <Label>{label}</Label>
      <Select value={settings[key]} onValueChange={(v) => set(key, v)}>
        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="auto">Automatic</SelectItem>
          <SelectItem value="semi">Semi-automatic</SelectItem>
          <SelectItem value="manual">Manual review</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );

  const numField = (label, key, step = 0.5, suffix = "%") => (
    <div>
      <Label>{label} {suffix && <span className="text-xs text-neutral-400">({suffix})</span>}</Label>
      <Input type="number" step={step} value={settings[key]} onChange={(e) => set(key, parseFloat(e.target.value))} className="mt-1" />
    </div>
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Platform settings</h2>
        <Button onClick={save} disabled={saving} className="bg-[#FF211F] hover:bg-[#e01d1b]">
          <Save className="h-4 w-4 mr-1" /> {saving ? "Saving…" : "Save"}
        </Button>
      </div>

      <div className="space-y-6">
        <section className="bg-white border border-neutral-200 rounded-lg p-5">
          <h3 className="font-semibold mb-3">Commissions & fees</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {numField("Platform fee", "platform_fee_pct")}
            {numField("Affiliate commission", "affiliate_commission_pct")}
            {numField("Referral L1", "referral_l1_pct")}
            {numField("Referral L2", "referral_l2_pct")}
            {numField("Referral L3", "referral_l3_pct")}
            {numField("Max dropship markup", "dropship_max_markup_pct")}
          </div>
          <div className="mt-4 flex items-center gap-2">
            <Switch checked={settings.referral_levels_enabled} onCheckedChange={(v) => set("referral_levels_enabled", v)} />
            <Label className="cursor-pointer">Enable multi-tier referral rewards</Label>
          </div>
        </section>

        <section className="bg-white border border-neutral-200 rounded-lg p-5" data-testid="settings-delivery-section">
          <h3 className="font-semibold mb-1">Delivery & fund release</h3>
          <p className="text-sm text-neutral-500 mb-3">
            Estimated shipping window shown to buyers on checkout & orders. Seller earnings stay frozen until the buyer confirms delivery, or the auto-release window elapses.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <Label>Delivery days estimate</Label>
              <Input
                type="number"
                min={1}
                step={1}
                value={settings.delivery_days_estimate ?? 7}
                onChange={(e) => set("delivery_days_estimate", parseInt(e.target.value, 10) || 7)}
                className="mt-1"
                data-testid="delivery-days-input"
              />
              <p className="text-xs text-neutral-500 mt-1">
                Buyers see &quot;Arrives in ~{settings.delivery_days_estimate ?? 7} days&quot; on checkout & orders.
              </p>
            </div>
            <div>
              <Label>Auto-release after (days)</Label>
              <Input
                type="number"
                min={1}
                step={1}
                value={settings.delivery_auto_release_days ?? 14}
                onChange={(e) => set("delivery_auto_release_days", parseInt(e.target.value, 10) || 14)}
                className="mt-1"
                data-testid="auto-release-days-input"
              />
              <p className="text-xs text-neutral-500 mt-1">
                If the buyer doesn&apos;t confirm delivery within this window, seller funds are released automatically.
              </p>
            </div>
          </div>
        </section>

        <section className="bg-white border border-neutral-200 rounded-lg p-5">
          <h3 className="font-semibold mb-3">Wallet & payouts</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {numField("Minimum withdrawal", "min_withdrawal", 1, "$")}
            {numField("Signup bonus", "signup_bonus", 1, "$")}
            {numField("Semi-auto threshold", "semi_threshold", 5, "$")}
          </div>
        </section>

        <section className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-5" data-testid="settings-invite-section">
          <h3 className="font-semibold mb-1 flex items-center gap-2">
            <Users className="h-4 w-4 text-amber-500" /> Signup access control
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            When enabled, new accounts can only register with a valid invitation code (an existing member&apos;s referral code). This turns Mercarie-Global into a closed, invite-only community until you flip it back off.
          </p>
          <div className="flex items-center justify-between gap-4 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 p-4">
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
                Invite-only registration
                <span className={`text-[10px] font-bold uppercase tracking-wider rounded-full px-2 py-0.5 ${
                  settings.invite_only_signup
                    ? "bg-amber-100 text-amber-800 border border-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:border-amber-800"
                    : "bg-emerald-100 text-emerald-800 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:border-emerald-800"
                }`}>
                  {settings.invite_only_signup ? "Closed" : "Open"}
                </span>
              </div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                {settings.invite_only_signup
                  ? "New signups must provide a valid invitation code. Registration without a code is blocked."
                  : "Anyone can register with or without an invitation code. Referral rewards still apply when a code is used."}
              </div>
            </div>
            <Switch
              checked={!!settings.invite_only_signup}
              onCheckedChange={(v) => set("invite_only_signup", v)}
              data-testid="invite-only-toggle"
            />
          </div>
        </section>

        <section className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-5" data-testid="settings-disputes-section">
          <h3 className="font-semibold mb-1 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-[#FF211F]" /> Disputes automation
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-3">
            Auto-refund any incoming dispute whose order amount is at or below this threshold, so your team only reviews the high-value cases. Set to 0 to disable and review every dispute manually.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <Label>Auto-refund threshold <span className="text-xs text-neutral-400">($)</span></Label>
              <Input
                type="number"
                step={1}
                min={0}
                value={settings.dispute_auto_refund_threshold ?? 0}
                onChange={(e) => set("dispute_auto_refund_threshold", parseFloat(e.target.value) || 0)}
                className="mt-1"
                data-testid="dispute-auto-refund-threshold-input"
                placeholder="0 = disabled"
              />
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {settings.dispute_auto_refund_threshold > 0
                  ? `Disputes on orders at or under $${Number(settings.dispute_auto_refund_threshold).toFixed(2)} will auto-refund the buyer.`
                  : "Auto-refund is off — all disputes go to your review queue."}
              </p>
            </div>
          </div>

          <div className="mt-5">
            <Label>Never auto-refund these reasons</Label>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
              High-fraud reasons stay in the manual queue even when under the threshold.
            </p>
            <div className="flex flex-wrap gap-2" data-testid="dispute-reason-exclusions">
              {[
                { value: "not_as_described", label: "Not as described" },
                { value: "damaged",          label: "Damaged" },
                { value: "not_received",     label: "Not received" },
                { value: "counterfeit",      label: "Counterfeit" },
                { value: "other",            label: "Other" },
              ].map((r) => {
                const excluded = (settings.dispute_auto_refund_excluded_reasons || []).includes(r.value);
                return (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => {
                      const cur = new Set(settings.dispute_auto_refund_excluded_reasons || []);
                      if (excluded) cur.delete(r.value); else cur.add(r.value);
                      set("dispute_auto_refund_excluded_reasons", Array.from(cur));
                    }}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border transition ${
                      excluded
                        ? "bg-[#FF211F] text-white border-[#FF211F] shadow-sm"
                        : "bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-200 border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18]"
                    }`}
                    data-testid={`exclusion-toggle-${r.value}`}
                  >
                    {excluded ? <XCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5 opacity-40" />}
                    {r.label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
              {(settings.dispute_auto_refund_excluded_reasons || []).length === 0
                ? "No exclusions — every eligible reason auto-refunds."
                : `${(settings.dispute_auto_refund_excluded_reasons || []).length} reason(s) will always go to manual review.`}
            </p>
          </div>
        </section>

        <section className="bg-white border border-neutral-200 rounded-lg p-5" data-testid="settings-bulk-tiers-section">
          <h3 className="font-semibold mb-1">Bulk discount tiers</h3>
          <p className="text-sm text-neutral-500 mb-3">
            Reward bulk buyers with an automatic percentage-off at checkout. When multiple tiers match a quantity the highest <code className="text-xs bg-neutral-100 px-1 rounded">min_qty</code> wins. Leave empty to disable bulk discounts entirely.
          </p>
          <div className="space-y-2" data-testid="bulk-tiers-list">
            {((settings.bulk_discount_tiers || [])).map((t, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3" data-testid={`bulk-tier-row-${i}`}>
                <div className="flex-1 grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-xs">Min quantity</Label>
                    <Input type="number" min={2} value={t.min_qty}
                      onChange={(e) => {
                        const v = parseInt(e.target.value) || 0;
                        const next = [...settings.bulk_discount_tiers];
                        next[i] = { ...next[i], min_qty: v };
                        set("bulk_discount_tiers", next);
                      }}
                      className="mt-1 h-9" data-testid={`bulk-tier-minqty-${i}`} />
                  </div>
                  <div>
                    <Label className="text-xs">Discount %</Label>
                    <Input type="number" step={0.5} min={0} max={90} value={t.discount_pct}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value) || 0;
                        const next = [...settings.bulk_discount_tiers];
                        next[i] = { ...next[i], discount_pct: v };
                        set("bulk_discount_tiers", next);
                      }}
                      className="mt-1 h-9" data-testid={`bulk-tier-pct-${i}`} />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => set("bulk_discount_tiers", settings.bulk_discount_tiers.filter((_, j) => j !== i))}
                  className="mt-4 h-9 px-3 rounded-md border border-red-200 text-red-600 hover:bg-red-50 text-xs font-semibold"
                  data-testid={`bulk-tier-remove-${i}`}
                >Remove</button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => set("bulk_discount_tiers", [...(settings.bulk_discount_tiers || []), { min_qty: 15, discount_pct: 15 }])}
            className="mt-3 h-9 px-4 rounded-md border border-neutral-200 hover:border-[#2563EB] hover:text-[#2563EB] text-sm font-semibold"
            data-testid="bulk-tier-add"
          >+ Add tier</button>
          {(settings.bulk_discount_tiers || []).length > 0 && (
            <div className="mt-4 text-xs rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 p-3">
              <b>Preview:</b>{" "}
              {[...settings.bulk_discount_tiers].sort((a,b) => a.min_qty - b.min_qty).map((t, i, arr) => (
                <span key={i}>{t.min_qty}+ units → {t.discount_pct}% off{i < arr.length - 1 ? " · " : ""}</span>
              ))}
            </div>
          )}
        </section>

        <section className="bg-white border border-neutral-200 rounded-lg p-5">
          <h3 className="font-semibold mb-3">Automation modes</h3>
          <p className="text-sm text-neutral-500 mb-3">Choose how new items are approved: instantly (auto), auto up to threshold (semi), or all manual.</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {modeField("New listings", "listing_mode")}
            {modeField("New stores", "store_mode")}
            {modeField("Affiliate signups", "affiliate_mode")}
            {modeField("Withdrawals", "withdrawal_mode")}
          </div>
        </section>
      </div>
    </div>
  );
};

const WithdrawalsMgr = () => {
  const [items, setItems] = useState([]);
  const { toast } = useToast();
  const load = () => api.get("/admin/withdrawals").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const process = async (wd, status) => {
    if (!window.confirm(`${status === "paid" ? "Mark as paid" : status === "rejected" ? "Reject" : "Approve"} ${formatPrice(wd.amount)} to ${wd.user_name}?`)) return;
    try {
      await api.put(`/admin/withdrawals/${wd.id}`, { status });
      toast({ title: `Marked ${status}` });
      load();
    } catch (err) {
      toast({ title: "Failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Withdrawals</h2>
      <div className="bg-white border border-neutral-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-3">User</th>
              <th className="p-3">Amount</th>
              <th className="p-3">Method</th>
              <th className="p-3">Account info</th>
              <th className="p-3">Status</th>
              <th className="p-3">Date</th>
              <th className="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-neutral-500">No withdrawal requests.</td></tr>
            )}
            {items.map((w) => (
              <tr key={w.id} className="border-t border-neutral-100">
                <td className="p-3 font-medium">{w.user_name}</td>
                <td className="p-3 font-medium">{formatPrice(w.amount)}</td>
                <td className="p-3 text-neutral-600 capitalize">{w.method.replace("_", " ")}</td>
                <td className="p-3 text-neutral-600 max-w-xs truncate">{w.account_info || "—"}</td>
                <td className="p-3"><Badge variant="secondary" className="capitalize">{w.status}</Badge></td>
                <td className="p-3 text-neutral-500 text-xs">{new Date(w.created_at).toLocaleString()}</td>
                <td className="p-3 text-right">
                  {w.status === "pending" && (
                    <div className="flex gap-1 justify-end">
                      <Button variant="outline" size="sm" onClick={() => process(w, "paid")}>
                        <Check className="h-3 w-3 mr-1" /> Pay
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => process(w, "rejected")}>
                        <XIcon className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                  {w.status === "approved" && (
                    <Button variant="outline" size="sm" onClick={() => process(w, "paid")}>
                      <Check className="h-3 w-3 mr-1" /> Mark paid
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const StoresMgr = () => {
  const [stores, setStores] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();
  const load = () => api.get("/admin/stores").then((r) => setStores(r.data));
  useEffect(() => { load(); }, []);

  const setTier = async (s, verified_tier) => {
    setStores((prev) => prev.map((x) => (x.id === s.id ? { ...x, verified_tier } : x)));
    try {
      await api.put(`/admin/stores/${s.id}`, { verified_tier });
      toast({ title: `Verified tier updated` });
    } catch { load(); }
  };
  const toggleActive = async (s) => {
    setStores((prev) => prev.map((x) => (x.id === s.id ? { ...x, is_active: !x.is_active } : x)));
    try { await api.put(`/admin/stores/${s.id}`, { is_active: !s.is_active }); }
    catch { load(); }
  };

  const onDragEnd = (result) => {
    if (!result.destination || result.source.index === result.destination.index) return;
    const copy = [...stores];
    const [moved] = copy.splice(result.source.index, 1);
    copy.splice(result.destination.index, 0, moved);
    setStores(copy);
    setDirty(true);
  };

  const saveOrder = async () => {
    setSaving(true);
    try {
      await api.post("/admin/stores/reorder", { ids: stores.map((s) => s.id) });
      toast({ title: "Storefront order saved" });
      setDirty(false);
    } catch {
      toast({ title: "Save failed", variant: "destructive" });
    } finally { setSaving(false); }
  };

  return (
    <div data-testid="admin-stores">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold">Stores</h2>
          <p className="text-sm text-neutral-500">Drag to reorder featured storefronts. Top of the list shows first everywhere.</p>
        </div>
        <Button
          onClick={saveOrder}
          disabled={saving || !dirty}
          className="bg-[#FF211F] hover:bg-[#e01d1b] gap-1.5 disabled:opacity-40"
          data-testid="save-store-order"
        >
          <Save className="h-4 w-4" /> {saving ? "Saving…" : dirty ? "Save order" : "Saved"}
        </Button>
      </div>

      {stores.length === 0 ? (
        <div className="bg-white border border-neutral-200 rounded-lg p-8 text-center text-neutral-500">No stores yet.</div>
      ) : (
        <DragDropContext onDragEnd={onDragEnd}>
          <Droppable droppableId="stores">
            {(provided) => (
              <div ref={provided.innerRef} {...provided.droppableProps} className="space-y-2">
                {stores.map((s, i) => (
                  <Draggable key={s.id} draggableId={s.id} index={i}>
                    {(prov, snapshot) => (
                      <div
                        ref={prov.innerRef}
                        {...prov.draggableProps}
                        className={`flex items-center gap-3 bg-white border rounded-lg p-3 ${snapshot.isDragging ? "border-[#FF7A18] shadow-lg" : "border-neutral-200"}`}
                        data-testid={`store-row-${s.id}`}
                      >
                        <span
                          {...prov.dragHandleProps}
                          className="cursor-grab active:cursor-grabbing text-neutral-400 hover:text-neutral-600"
                          data-testid={`store-drag-${s.id}`}
                        >
                          <GripVertical className="h-4 w-4" />
                        </span>
                        <div className="w-8 h-8 rounded-lg bg-neutral-100 grid place-items-center overflow-hidden shrink-0">
                          {s.logo ? (
                            <img src={s.logo} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <StoreIcon className="h-4 w-4 text-neutral-400" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0 grid sm:grid-cols-[minmax(0,1fr)_auto_auto_auto_auto] items-center gap-3">
                          <div className="min-w-0">
                            <div className="font-semibold truncate">{s.name}</div>
                            <div className="text-xs text-neutral-500 font-mono truncate">/{s.slug}</div>
                          </div>
                          <div className="text-xs text-neutral-500 whitespace-nowrap">
                            {s.total_sales} sales · {s.followers_count} followers
                          </div>
                          <Select value={s.verified_tier} onValueChange={(v) => setTier(s, v)}>
                            <SelectTrigger className="h-8 w-28" data-testid={`store-tier-${s.id}`}><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">None</SelectItem>
                              <SelectItem value="bronze">Bronze</SelectItem>
                              <SelectItem value="silver">Silver</SelectItem>
                              <SelectItem value="gold">Gold</SelectItem>
                            </SelectContent>
                          </Select>
                          <div className="flex items-center gap-2">
                            <Switch
                              checked={s.is_active}
                              onCheckedChange={() => toggleActive(s)}
                              data-testid={`store-toggle-${s.id}`}
                            />
                            <span className="text-xs text-neutral-500">{s.is_active ? "Active" : "Off"}</span>
                          </div>
                          <div className="text-[11px] text-neutral-400 whitespace-nowrap">{new Date(s.created_at).toLocaleDateString()}</div>
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
      )}
      <p className="text-xs text-neutral-500 mt-4">Drag rows to reorder, then Save. This controls the order storefronts appear on the Home page and any &ldquo;featured stores&rdquo; strips.</p>
    </div>
  );
};

const SellerApplicationsMgr = () => {
  const [apps, setApps] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [notesById, setNotesById] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [bulkNotes, setBulkNotes] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const { toast } = useToast();

  const load = () => {
    const params = filter && filter !== "all" ? { status_filter: filter } : {};
    api.get("/admin/seller-applications", { params }).then((r) => {
      setApps(r.data);
      setSelected(new Set());
    });
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const review = async (id, status) => {
    const admin_notes = notesById[id] || "";
    try {
      await api.put(`/admin/seller-applications/${id}`, { status, admin_notes });
      toast({ title: `Application ${status}` });
      load();
    } catch (err) {
      toast({ title: "Failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };

  const pendingApps = apps.filter((a) => a.status === "pending");
  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const selectAllPending = () => setSelected(new Set(pendingApps.map((a) => a.id)));
  const clearSelected = () => setSelected(new Set());

  const bulkReview = async (status) => {
    if (selected.size === 0) return;
    if (!window.confirm(`${status === "approved" ? "Approve" : "Reject"} ${selected.size} application${selected.size === 1 ? "" : "s"}?`)) return;
    setBulkBusy(true);
    try {
      const { data } = await api.post("/admin/seller-applications/bulk-review", {
        ids: Array.from(selected), status, admin_notes: bulkNotes,
      });
      toast({
        title: `${data.processed} ${status}`,
        description: data.skipped_count ? `${data.skipped_count} skipped (already reviewed)` : "All done.",
      });
      setBulkNotes("");
      load();
    } catch (err) {
      toast({ title: "Bulk review failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setBulkBusy(false);
    }
  };

  return (
    <div data-testid="admin-seller-apps">
      <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
        <h2 className="text-2xl font-bold">Seller applications</h2>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-40" data-testid="apps-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {pendingApps.length > 0 && (
        <div className="mb-4 sticky top-2 z-10 rounded-xl border border-neutral-200 bg-white/95 backdrop-blur p-3 flex flex-col sm:flex-row sm:items-center gap-2 shadow-sm" data-testid="apps-bulk-bar">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={selected.size === pendingApps.length ? clearSelected : selectAllPending}
              className="min-h-[36px] px-3 rounded-full text-xs font-semibold border border-neutral-200 hover:border-emerald-500 hover:text-emerald-600 transition"
              data-testid="apps-select-all"
            >
              {selected.size === pendingApps.length ? "Clear all" : `Select all pending (${pendingApps.length})`}
            </button>
            <span className="text-xs text-neutral-600 font-semibold" data-testid="apps-selected-count">
              {selected.size} selected
            </span>
          </div>
          <Input
            placeholder="Bulk notes (optional, applied to all)"
            value={bulkNotes}
            onChange={(e) => setBulkNotes(e.target.value)}
            className="flex-1 min-w-0 h-10"
            data-testid="apps-bulk-notes"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => bulkReview("approved")}
              disabled={selected.size === 0 || bulkBusy}
              className="min-h-[40px] bg-emerald-600 hover:bg-emerald-700"
              data-testid="apps-bulk-approve"
            ><Check className="h-4 w-4 mr-1" /> {bulkBusy ? "Working…" : "Approve selected"}</Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkReview("rejected")}
              disabled={selected.size === 0 || bulkBusy}
              className="min-h-[40px]"
              data-testid="apps-bulk-reject"
            ><XIcon className="h-4 w-4 mr-1" /> Reject</Button>
          </div>
        </div>
      )}

      {apps.length === 0 && <div className="text-neutral-500 text-sm">No applications match this filter.</div>}
      <div className="space-y-3">
        {apps.map((a) => (
          <div key={a.id} className={`bg-white border rounded-lg p-4 transition ${selected.has(a.id) ? "border-emerald-500 ring-2 ring-emerald-500/20" : "border-neutral-200"}`} data-testid={`app-row-${a.id}`}>
            <div className="flex items-start gap-3">
              {a.status === "pending" && (
                <button
                  type="button"
                  onClick={() => toggle(a.id)}
                  className="min-h-[44px] min-w-[44px] grid place-items-center -m-2 shrink-0"
                  aria-label={selected.has(a.id) ? "Deselect" : "Select"}
                  data-testid={`app-check-${a.id}`}
                >
                  {selected.has(a.id) ? <CheckSquare className="h-5 w-5 text-emerald-600" /> : <SquareIcon className="h-5 w-5 text-neutral-400" />}
                </button>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{a.legal_name} <span className="text-neutral-400 text-sm">({a.user_username})</span></div>
                <div className="text-xs text-neutral-500">{a.user_email} · {a.business_type} · {a.business_name || "—"}</div>
                <div className="text-xs text-neutral-500 mt-1">
                  {a.address_line1}, {a.city}, {a.state} {a.postal_code} · {a.country}
                </div>
                <div className="text-xs text-neutral-500 mt-1">Tax ID: {a.tax_id || "—"} · Payout: {a.payout_method} · Phone: {a.phone}</div>
                <div className="text-xs text-neutral-400 mt-1">Submitted {new Date(a.created_at).toLocaleString()}</div>
              </div>
              <Badge className={`capitalize ${a.status === "pending" ? "bg-amber-100 text-amber-800" : a.status === "approved" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"} hover:opacity-100 shrink-0`}>{a.status}</Badge>
            </div>
            {a.status === "pending" && (
              <div className="mt-3 flex flex-col sm:flex-row gap-2 sm:items-center">
                <Input
                  placeholder="Admin notes (optional)"
                  value={notesById[a.id] || ""}
                  onChange={(e) => setNotesById({ ...notesById, [a.id]: e.target.value })}
                  data-testid={`app-notes-${a.id}`}
                />
                <Button size="sm" onClick={() => review(a.id, "approved")} className="bg-emerald-600 hover:bg-emerald-700" data-testid={`app-approve-${a.id}`}>
                  <Check className="h-4 w-4 mr-1" /> Approve
                </Button>
                <Button size="sm" variant="outline" onClick={() => review(a.id, "rejected")} data-testid={`app-reject-${a.id}`}>
                  <XIcon className="h-4 w-4 mr-1" /> Reject
                </Button>
              </div>
            )}
            {a.admin_notes && a.status !== "pending" && (
              <div className="mt-3 text-xs text-neutral-600 border-t border-neutral-100 pt-2">Notes: {a.admin_notes}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const DISPUTE_REASON_LABEL = {
  not_as_described: "Not as described",
  damaged: "Damaged",
  not_received: "Not received",
  counterfeit: "Counterfeit",
  other: "Other",
};

const DISPUTE_STATUS_BADGE = {
  open:      { label: "Open",      Icon: Clock,        cls: "bg-amber-100 text-amber-800 border-amber-200" },
  reviewing: { label: "Reviewing", Icon: ShieldAlert,  cls: "bg-sky-100 text-sky-800 border-sky-200" },
  refunded:  { label: "Refunded",  Icon: CheckCircle2, cls: "bg-emerald-100 text-emerald-800 border-emerald-200" },
  rejected:  { label: "Rejected",  Icon: XCircle,      cls: "bg-rose-100 text-rose-800 border-rose-200" },
};

const DisputesMgr = () => {
  const [disputes, setDisputes] = useState([]);
  const [filter, setFilter] = useState("open");
  const [notesById, setNotesById] = useState({});
  const [resolutionById, setResolutionById] = useState({});
  const [busyId, setBusyId] = useState(null);
  const { toast } = useToast();

  const load = () => {
    const params = filter === "all" ? {} : { status: filter };
    api.get("/admin/disputes", { params }).then((r) => setDisputes(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const resolve = async (d, action) => {
    setBusyId(d.id);
    try {
      const payload = {
        action,
        admin_notes: notesById[d.id] ?? d.admin_notes ?? "",
        resolution: resolutionById[d.id] ?? d.resolution ?? "",
      };
      await api.post(`/admin/disputes/${d.id}/resolve`, payload);
      toast({
        title: action === "refund" ? "Refund issued" : action === "reject" ? "Dispute rejected" : "Marked as reviewing",
      });
      load();
    } catch (e) {
      toast({ title: "Action failed", description: e?.response?.data?.detail || "Try again.", variant: "destructive" });
    } finally { setBusyId(null); }
  };

  return (
    <div data-testid="admin-disputes">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-[#FF211F]" /> Disputes
          </h2>
          <p className="text-sm text-neutral-500">Review buyer disputes. Refund credits the buyer wallet and cancels the order.</p>
        </div>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-40" data-testid="dispute-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="reviewing">Reviewing</SelectItem>
            <SelectItem value="refunded">Refunded</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {disputes.length === 0 ? (
        <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-10 text-center text-neutral-500 dark:text-neutral-400" data-testid="admin-disputes-empty">
          No disputes in this bucket.
        </div>
      ) : (
        <div className="space-y-3">
          {disputes.map((d) => {
            const meta = DISPUTE_STATUS_BADGE[d.status] || DISPUTE_STATUS_BADGE.open;
            const Icon = meta.Icon;
            const closed = ["refunded", "rejected"].includes(d.status);
            return (
              <div
                key={d.id}
                className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl p-4"
                data-testid={`admin-dispute-${d.id}`}
              >
                <div className="flex flex-wrap items-start gap-4">
                  <img
                    src={d.listing_image} alt=""
                    className="h-16 w-16 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${meta.cls}`}>
                        <Icon className="h-3 w-3" /> {meta.label}
                      </span>
                      <Badge variant="outline" className="text-xs">{DISPUTE_REASON_LABEL[d.reason] || d.reason}</Badge>
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        {new Date(d.created_at).toLocaleDateString()} · #{d.id.slice(0, 6)}
                      </span>
                    </div>
                    <div className="mt-1 font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-1">{d.listing_title}</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400">
                      Buyer <span className="font-medium">{d.buyer_name}</span> · Order #{d.order_id.slice(0, 6)} · {formatPrice(d.amount)}
                    </div>
                  </div>
                </div>
                <p className="mt-3 text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">{d.description}</p>

                {d.photos?.length > 0 && (
                  <div className="mt-3 grid grid-cols-6 gap-2">
                    {d.photos.map((url, i) => (
                      <a
                        key={i}
                        href={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari-global_token") || ""}`}
                        target="_blank" rel="noreferrer"
                        className="block aspect-square rounded-lg overflow-hidden bg-neutral-100 hover:ring-2 hover:ring-[#FF7A18]"
                        data-testid={`admin-dispute-photo-${d.id}-${i}`}
                      >
                        <img
                          src={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari-global_token") || ""}`}
                          alt="evidence" className="h-full w-full object-cover"
                        />
                      </a>
                    ))}
                  </div>
                )}

                {!closed ? (
                  <div className="mt-4 grid md:grid-cols-2 gap-3">
                    <Input
                      placeholder="Buyer-facing resolution (optional)"
                      value={resolutionById[d.id] ?? d.resolution ?? ""}
                      onChange={(e) => setResolutionById({ ...resolutionById, [d.id]: e.target.value })}
                      data-testid={`dispute-resolution-${d.id}`}
                    />
                    <Input
                      placeholder="Internal notes (optional)"
                      value={notesById[d.id] ?? d.admin_notes ?? ""}
                      onChange={(e) => setNotesById({ ...notesById, [d.id]: e.target.value })}
                      data-testid={`dispute-notes-${d.id}`}
                    />
                    <div className="md:col-span-2 flex flex-wrap gap-2">
                      <Button
                        size="sm" onClick={() => resolve(d, "refund")}
                        className="bg-emerald-600 hover:bg-emerald-700"
                        disabled={busyId === d.id}
                        data-testid={`dispute-refund-${d.id}`}
                      >
                        <CheckCircle2 className="h-4 w-4 mr-1" /> Refund buyer
                      </Button>
                      <Button
                        size="sm" variant="outline"
                        onClick={() => resolve(d, "reject")}
                        disabled={busyId === d.id}
                        data-testid={`dispute-reject-${d.id}`}
                      >
                        <XCircle className="h-4 w-4 mr-1" /> Side with seller
                      </Button>
                      {d.status === "open" && (
                        <Button
                          size="sm" variant="outline"
                          onClick={() => resolve(d, "review")}
                          disabled={busyId === d.id}
                          data-testid={`dispute-review-${d.id}`}
                        >
                          <ShieldAlert className="h-4 w-4 mr-1" /> Mark reviewing
                        </Button>
                      )}
                    </div>
                  </div>
                ) : null}
                {closed ? (
                  <div className="mt-3 text-xs text-neutral-500 dark:text-neutral-400 border-t border-neutral-100 dark:border-neutral-800 pt-2 space-y-1">
                    {d.resolution && <div><span className="font-medium">Resolution:</span> {d.resolution}</div>}
                    {d.admin_notes && <div><span className="font-medium">Notes:</span> {d.admin_notes}</div>}
                    {d.resolved_at && <div>Closed on {new Date(d.resolved_at).toLocaleDateString()}</div>}
                  </div>
                ) : null}

                <AdminDisputeThread disputeId={d.id} closed={closed} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// -- Compact admin-side chat thread reused inside DisputesMgr -----------------
const AdminDisputeThread = ({ disputeId, closed }) => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const { toast } = useToast();

  const load = React.useCallback(async () => {
    try {
      const r = await api.get(`/disputes/${disputeId}/messages`);
      setMessages(r.data);
    } catch { /* noop */ }
  }, [disputeId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const send = async () => {
    const trimmed = body.trim();
    if (!trimmed) return;
    setSending(true);
    try {
      await api.post(`/disputes/${disputeId}/messages`, { body: trimmed, photos: [] });
      setBody("");
      await load();
    } catch (e) {
      toast({ title: "Message failed", description: e?.response?.data?.detail || "Try again.", variant: "destructive" });
    } finally { setSending(false); }
  };

  return (
    <div className="mt-3 border-t border-neutral-200 dark:border-neutral-800 pt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-[#FF7A18] hover:text-[#FF211F] transition"
        data-testid={`admin-dispute-thread-toggle-${disputeId}`}
      >
        <MessageCircle className="h-4 w-4" />
        {open ? "Hide thread" : "View & message thread"}
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
      {open && (
        <div className="mt-3">
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1 mb-2">
            {messages.length === 0 && (
              <p className="text-sm text-neutral-500 dark:text-neutral-400 py-2 text-center">No messages yet.</p>
            )}
            {messages.map((m) => {
              const mine = m.sender_id === user?.id;
              const role = m.sender_role || "buyer";
              return (
                <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                    mine
                      ? "bg-[#FF211F] text-white rounded-br-md"
                      : role === "seller"
                        ? "bg-emerald-50 dark:bg-emerald-500/15 text-neutral-900 dark:text-neutral-100 rounded-bl-md"
                        : "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-bl-md"
                  }`}>
                    <div className={`text-[10px] font-medium mb-0.5 ${mine ? "opacity-80" : "text-neutral-500 dark:text-neutral-400"}`}>
                      {role === "admin" ? "Support" : role === "seller" ? "Seller" : "Buyer"} · {m.sender_name} · {new Date(m.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                    </div>
                    {m.body && <div className="whitespace-pre-wrap leading-snug">{m.body}</div>}
                    {m.photos?.length > 0 && (
                      <div className="mt-1.5 grid grid-cols-2 gap-1">
                        {m.photos.map((url, i) => (
                          <a key={i} href={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari-global_token") || ""}`} target="_blank" rel="noreferrer" className="block aspect-square rounded-md overflow-hidden">
                            <img src={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari-global_token") || ""}`} alt="" className="h-full w-full object-cover" />
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {!closed && (
            <div className="flex gap-2">
              <Input
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Post a support message to both parties…"
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                data-testid={`admin-dispute-msg-input-${disputeId}`}
              />
              <Button
                onClick={send}
                disabled={sending || !body.trim()}
                className="bg-[#FF211F] hover:bg-[#e01d1b] shrink-0"
                data-testid={`admin-dispute-msg-send-${disputeId}`}
              >
                <MessageCircle className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const Admin = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!loading && (!user || user.role !== "admin")) navigate("/");
  }, [user, loading, navigate]);

  if (loading || !user) return <div className="p-8">Loading…</div>;
  if (user.role !== "admin") return <Navigate to="/" />;

  return <AdminShell />;
};

const AdminSidebarNav = ({ compact = false }) => (
  <nav className={compact ? "space-y-1 p-4" : "space-y-1"} data-testid={compact ? "admin-drawer-nav" : "admin-sidebar-nav"}>
    <div className="px-3 py-2 mb-2">
      <div className="text-xs text-neutral-500 uppercase tracking-wider">Admin panel</div>
    </div>
    <SidebarLink to="/admin" icon={LayoutDashboard}>Dashboard</SidebarLink>
    <SidebarLink to="/admin/users" icon={Users}>Users</SidebarLink>
    <SidebarLink to="/admin/stores" icon={StoreIcon}>Stores</SidebarLink>
    <SidebarLink to="/admin/listings" icon={Package}>Listings</SidebarLink>
    <SidebarLink to="/admin/products" icon={Package}>Products (catalog)</SidebarLink>
    <SidebarLink to="/admin/search-insights" icon={Package}>Search insights</SidebarLink>
    <SidebarLink to="/admin/orders" icon={ShoppingBag}>Orders</SidebarLink>
    <SidebarLink to="/admin/categories" icon={FolderTree}>Categories</SidebarLink>
    <SidebarLink to="/admin/withdrawals" icon={Wallet}>Withdrawals</SidebarLink>
    <SidebarLink to="/admin/payment-reviews" icon={ShieldAlert}>Payment reviews</SidebarLink>
    <SidebarLink to="/admin/ledger-audit" icon={Wallet}>Ledger audit</SidebarLink>
    <SidebarLink to="/admin/payment-methods" icon={Bitcoin}>Payment methods</SidebarLink>
    <SidebarLink to="/admin/coupons" icon={Ticket}>Coupons</SidebarLink>
    <SidebarLink to="/admin/disputes" icon={AlertCircle}>Disputes</SidebarLink>
    <SidebarLink to="/admin/seller-applications" icon={IdCard}>Seller applications</SidebarLink>
    <SidebarLink to="/admin/shelves" icon={LayoutGrid}>Homepage shelves</SidebarLink>
    <SidebarLink to="/admin/apify-sync" icon={Database}>Apify sync</SidebarLink>
    <SidebarLink to="/admin/store-boosts" icon={StoreIcon}>Store boosts</SidebarLink>
    <SidebarSupportLink />
    <SidebarLink to="/admin/email-log" icon={Mail}>Email log</SidebarLink>
    <SidebarLink to="/admin/settings" icon={SettingsIcon}>Settings</SidebarLink>
  </nav>
);

const AdminShell = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Close drawer whenever route changes so tapping a link on mobile dismisses it.
  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 md:py-8">
      {/* Mobile top bar with hamburger — visible only <768px */}
      <div className="md:hidden flex items-center justify-between mb-4">
        <div className="text-xs text-neutral-500 uppercase tracking-wider font-semibold">Admin</div>
        <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1.5 min-h-[44px]" data-testid="admin-drawer-open">
              <Menu className="h-4 w-4" /> Menu
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="p-0 w-[280px] overflow-y-auto">
            <SheetTitle className="sr-only">Admin navigation</SheetTitle>
            <AdminSidebarNav compact />
          </SheetContent>
        </Sheet>
      </div>
      <div className="grid md:grid-cols-[220px_1fr] gap-4 md:gap-8">
        {/* Desktop sidebar — hidden <768px */}
        <aside className="hidden md:block">
          <AdminSidebarNav />
        </aside>
        <main className="min-w-0">
          <Routes>
            <Route index element={<Dashboard />} />
            <Route path="users" element={<UsersMgr />} />
            <Route path="stores" element={<StoresMgr />} />
            <Route path="listings" element={<ListingsMgr />} />
            <Route path="products" element={<AdminProducts />} />
            <Route path="search-insights" element={<AdminSearchInsights />} />
            <Route path="orders" element={<OrdersMgr />} />
            <Route path="categories" element={<CategoriesMgr />} />
            <Route path="withdrawals" element={<WithdrawalsMgr />} />
            <Route path="payment-reviews" element={<AdminPaymentReviews />} />
            <Route path="ledger-audit" element={<AdminLedgerAudit />} />
            <Route path="payment-methods" element={<AdminPaymentMethods />} />
            <Route path="disputes" element={<DisputesMgr />} />
            <Route path="seller-applications" element={<SellerApplicationsMgr />} />
            <Route path="shelves" element={<AdminShelves />} />
            <Route path="apify-sync" element={<ApifySync />} />
            <Route path="store-boosts" element={<AdminStoreBoosts />} />
            <Route path="support-tickets" element={<AdminSupport />} />
            <Route path="email-log" element={<AdminEmailLog />} />
            <Route path="settings" element={<SettingsMgr />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export default Admin;
