import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
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
  Package,
  Search as SearchIcon,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Trash2,
  ExternalLink,
} from "lucide-react";

const PAGE_SIZE = 25;

const money = (a, c = "USD") => {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: c,
      maximumFractionDigits: 2,
    }).format(a);
  } catch {
    return `$${Number(a).toFixed(2)}`;
  }
};

const EditProductDialog = ({ open, product, onClose, onSaved }) => {
  const { toast } = useToast();
  const [form, setForm] = useState(product);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(product);
  }, [product]);

  if (!product) return null;

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        description: form.description || "",
        price: Number(form.price),
        currency: form.currency,
        category: form.category || null,
        sku: form.sku || null,
        source_url: form.source_url || null,
        images: (form.images || []).filter(Boolean),
        is_active: !!form.is_active,
      };
      const { data } = await api.patch(`/admin/products/${product.id}`, payload);
      toast({ title: "Product updated" });
      onSaved(data);
      onClose();
    } catch (err) {
      toast({
        title: "Update failed",
        description: err.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="admin-product-edit-dialog">
        <DialogHeader>
          <DialogTitle>Edit product</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Title</Label>
            <Input
              value={form.title || ""}
              onChange={(e) => set("title", e.target.value)}
              data-testid="edit-product-title"
            />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              rows={4}
              value={form.description || ""}
              onChange={(e) => set("description", e.target.value)}
              data-testid="edit-product-description"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Price</Label>
              <Input
                type="number"
                step="0.01"
                value={form.price || 0}
                onChange={(e) => set("price", e.target.value)}
                data-testid="edit-product-price"
              />
            </div>
            <div>
              <Label>Currency</Label>
              <Input
                value={form.currency || "USD"}
                onChange={(e) => set("currency", e.target.value.toUpperCase())}
                data-testid="edit-product-currency"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Category</Label>
              <Input
                value={form.category || ""}
                onChange={(e) => set("category", e.target.value)}
                data-testid="edit-product-category"
              />
            </div>
            <div>
              <Label>SKU</Label>
              <Input
                value={form.sku || ""}
                onChange={(e) => set("sku", e.target.value)}
                data-testid="edit-product-sku"
              />
            </div>
          </div>
          <div>
            <Label>Source URL</Label>
            <Input
              value={form.source_url || ""}
              onChange={(e) => set("source_url", e.target.value)}
              data-testid="edit-product-source-url"
            />
          </div>
          <div>
            <Label>Images (one URL per line)</Label>
            <Textarea
              rows={3}
              value={(form.images || []).join("\n")}
              onChange={(e) =>
                set(
                  "images",
                  e.target.value.split("\n").map((s) => s.trim())
                )
              }
              data-testid="edit-product-images"
            />
          </div>
          <div className="flex items-center justify-between p-3 bg-neutral-50 dark:bg-neutral-800/60 rounded-lg">
            <div>
              <Label className="text-sm">Active on storefront</Label>
              <p className="text-xs text-neutral-500 mt-0.5">
                Inactive products are hidden from public listings
              </p>
            </div>
            <Switch
              checked={!!form.is_active}
              onCheckedChange={(v) => set("is_active", v)}
              data-testid="edit-product-active-switch"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={save}
            disabled={saving}
            className="bg-[#FF211F] hover:bg-[#e01d1b]"
            data-testid="edit-product-save-btn"
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const AdminProducts = () => {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [qDraft, setQDraft] = useState("");
  const [status, setStatus] = useState("all");
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get("/admin/products", {
        params: { page, page_size: PAGE_SIZE, ...(q ? { q } : {}), status },
      });
      setData(res);
    } catch (err) {
      toast({
        title: "Failed to load",
        description: err.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [page, q, status, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const toggleActive = async (p, next) => {
    // Optimistic update
    setData((d) => ({
      ...d,
      items: d.items.map((x) => (x.id === p.id ? { ...x, is_active: next } : x)),
    }));
    try {
      await api.patch(`/admin/products/${p.id}`, { is_active: next });
      toast({
        title: next ? "Product activated" : "Product hidden",
        description: p.title,
      });
    } catch (err) {
      // Rollback
      setData((d) => ({
        ...d,
        items: d.items.map((x) =>
          x.id === p.id ? { ...x, is_active: !next } : x
        ),
      }));
      toast({
        title: "Toggle failed",
        description: err.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    }
  };

  const removeProduct = async (p) => {
    if (
      !window.confirm(
        `Permanently delete "${p.title}"? This cannot be undone — consider using the Active toggle to hide it instead.`
      )
    ) {
      return;
    }
    try {
      await api.delete(`/admin/products/${p.id}`);
      toast({ title: "Product deleted" });
      load();
    } catch (err) {
      toast({
        title: "Delete failed",
        description: err.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    }
  };

  const submitSearch = (e) => {
    e.preventDefault();
    setPage(1);
    setQ(qDraft);
  };

  return (
    <div data-testid="admin-products-page">
      <div className="flex items-center gap-2 mb-4">
        <Package className="h-6 w-6 text-[#FF211F]" />
        <h2 className="text-2xl font-bold">Products</h2>
        {data ? (
          <Badge variant="outline" className="ml-2">
            {data.total.toLocaleString()} total
          </Badge>
        ) : null}
      </div>
      <p className="text-neutral-600 dark:text-neutral-400 mb-6 text-sm">
        Permanent catalog imported via the Apify webhook. Toggle Active to hide
        items from the public storefront, or click Edit to change any field.
      </p>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <form onSubmit={submitSearch} className="flex items-center gap-2 flex-1">
          <div className="relative flex-1 max-w-md">
            <SearchIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
            <Input
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
              placeholder="Search by title or SKU…"
              className="pl-9"
              data-testid="admin-products-search-input"
            />
          </div>
          <Button
            type="submit"
            variant="outline"
            data-testid="admin-products-search-btn"
          >
            Search
          </Button>
        </form>
        <Select
          value={status}
          onValueChange={(v) => {
            setPage(1);
            setStatus(v);
          }}
        >
          <SelectTrigger className="w-40" data-testid="admin-products-status-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active only</SelectItem>
            <SelectItem value="inactive">Inactive only</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="admin-products-table">
            <thead className="bg-neutral-50 dark:bg-neutral-800/60 text-left text-neutral-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="p-3 w-14"> </th>
                <th className="p-3">Title</th>
                <th className="p-3">Category</th>
                <th className="p-3">SKU</th>
                <th className="p-3 text-right">Price</th>
                <th className="p-3 text-center">Active</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {loading && !data ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-neutral-500">
                    Loading…
                  </td>
                </tr>
              ) : data?.items.length ? (
                data.items.map((p) => (
                  <tr
                    key={p.id}
                    className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
                    data-testid={`admin-product-row-${p.id}`}
                  >
                    <td className="p-3">
                      <div className="h-10 w-10 rounded-lg bg-neutral-100 dark:bg-neutral-800 overflow-hidden grid place-items-center">
                        {p.images?.[0] ? (
                          <img
                            src={p.images[0]}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <Package className="h-4 w-4 text-neutral-400" />
                        )}
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="font-medium text-neutral-900 dark:text-neutral-100 line-clamp-1 max-w-[380px]">
                        {p.title}
                      </div>
                      {p.source_url ? (
                        <a
                          href={p.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] text-neutral-400 hover:text-[#FF211F] inline-flex items-center gap-1 mt-0.5"
                        >
                          source <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : null}
                    </td>
                    <td className="p-3 text-neutral-600 dark:text-neutral-300">
                      {p.category || <span className="text-neutral-400">—</span>}
                    </td>
                    <td className="p-3 font-mono text-xs text-neutral-500 max-w-[140px] truncate">
                      {p.sku || "—"}
                    </td>
                    <td className="p-3 text-right font-semibold tabular-nums">
                      {money(p.price, p.currency)}
                    </td>
                    <td className="p-3 text-center">
                      <Switch
                        checked={!!p.is_active}
                        onCheckedChange={(v) => toggleActive(p, v)}
                        data-testid={`admin-product-active-toggle-${p.id}`}
                      />
                    </td>
                    <td className="p-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditing(p)}
                          data-testid={`admin-product-edit-btn-${p.id}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => removeProduct(p)}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
                          data-testid={`admin-product-delete-btn-${p.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="p-8 text-center">
                    <Package className="h-8 w-8 text-neutral-300 mx-auto mb-2" />
                    <p className="text-neutral-500">No products match your filters</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {data && totalPages > 1 ? (
          <div
            className="flex items-center justify-between p-3 border-t border-neutral-200 dark:border-neutral-800"
            data-testid="admin-products-pagination"
          >
            <div className="text-xs text-neutral-500">
              Page {page} of {totalPages} · {data.total.toLocaleString()} total
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                data-testid="admin-products-prev-btn"
              >
                <ChevronLeft className="h-4 w-4" /> Prev
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                data-testid="admin-products-next-btn"
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <EditProductDialog
        open={!!editing}
        product={editing}
        onClose={() => setEditing(null)}
        onSaved={(updated) =>
          setData((d) => ({
            ...d,
            items: d.items.map((x) => (x.id === updated.id ? updated : x)),
          }))
        }
      />
    </div>
  );
};

export default AdminProducts;
