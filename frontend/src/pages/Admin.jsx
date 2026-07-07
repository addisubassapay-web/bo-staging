import React, { useEffect, useState } from "react";
import { NavLink, Route, Routes, Navigate, useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { LayoutDashboard, Users, Package, ShoppingBag, FolderTree, Trash2, Star, Plus } from "lucide-react";

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
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard label="Users" value={stats.users} />
        <StatCard label="Active listings" value={stats.active_listings} />
        <StatCard label="Sold listings" value={stats.sold_listings} />
        <StatCard label="Orders" value={stats.orders} />
        <StatCard label="Categories" value={stats.categories} />
        <StatCard label="Total revenue" value={formatPrice(stats.revenue)} hint="Across all completed orders" />
      </div>
    </div>
  );
};

const UsersMgr = () => {
  const [users, setUsers] = useState([]);
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

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Users</h2>
      <div className="bg-white border border-neutral-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-3">User</th>
              <th className="p-3">Email</th>
              <th className="p-3">Role</th>
              <th className="p-3">Sales</th>
              <th className="p-3">Status</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-neutral-100">
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
                  <div className="flex items-center gap-2">
                    <Switch checked={u.is_active} onCheckedChange={() => toggleActive(u)} />
                    <span className="text-xs text-neutral-500">{u.is_active ? "Active" : "Disabled"}</span>
                  </div>
                </td>
                <td className="p-3 text-right">
                  <Button variant="ghost" size="sm" onClick={() => del(u)}><Trash2 className="h-4 w-4 text-neutral-500" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

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
      <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden">
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

const Admin = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!loading && (!user || user.role !== "admin")) navigate("/");
  }, [user, loading, navigate]);

  if (loading || !user) return <div className="p-8">Loading…</div>;
  if (user.role !== "admin") return <Navigate to="/" />;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 grid md:grid-cols-[220px_1fr] gap-8">
      <aside className="space-y-1">
        <div className="px-3 py-2 mb-2">
          <div className="text-xs text-neutral-500 uppercase tracking-wider">Admin panel</div>
        </div>
        <SidebarLink to="/admin" icon={LayoutDashboard}>Dashboard</SidebarLink>
        <SidebarLink to="/admin/users" icon={Users}>Users</SidebarLink>
        <SidebarLink to="/admin/listings" icon={Package}>Listings</SidebarLink>
        <SidebarLink to="/admin/orders" icon={ShoppingBag}>Orders</SidebarLink>
        <SidebarLink to="/admin/categories" icon={FolderTree}>Categories</SidebarLink>
      </aside>
      <main>
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="users" element={<UsersMgr />} />
          <Route path="listings" element={<ListingsMgr />} />
          <Route path="orders" element={<OrdersMgr />} />
          <Route path="categories" element={<CategoriesMgr />} />
        </Routes>
      </main>
    </div>
  );
};

export default Admin;
