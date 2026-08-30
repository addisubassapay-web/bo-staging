import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const EditListing = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const [categories, setCategories] = useState([]);
  const [listing, setListing] = useState(null);
  const [selectedPhotoIdx, setSelectedPhotoIdx] = useState(0);
  const [form, setForm] = useState({
    title: "", description: "", price: "", original_price: "",
    category_id: "", condition: "good", brand: "", size: "", color: "",
    shipping_paid_by: "seller", shipping_method: "Standard",
  });
  const [saving, setSaving] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/categories").then((r) => setCategories(r.data));
    api.get(`/listings/${id}`).then((r) => {
      const l = r.data;
      setListing(l);
      // Ownership check
      if (l.seller_id !== user.id && user.role !== "admin") {
        toast({ title: "Not your listing", variant: "destructive" });
        navigate("/profile");
        return;
      }
      setForm({
        title: l.title || "", description: l.description || "",
        price: String(l.price ?? ""), original_price: String(l.original_price ?? ""),
        category_id: l.category_id || "", condition: l.condition || "good",
        brand: l.brand || "", size: l.size || "", color: l.color || "",
        shipping_paid_by: l.shipping_paid_by || "seller",
        shipping_method: l.shipping_method || "Standard",
      });
    }).catch(() => {
      toast({ title: "Listing not found", variant: "destructive" });
      navigate("/profile");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, user, authLoading]);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: typeof v === "string" ? v : v.target.value }));

  const regenerate = async () => {
    if (!listing?.images?.length) {
      toast({ title: "This listing has no images", variant: "destructive" });
      return;
    }
    const imageUrl = listing.images[selectedPhotoIdx] || listing.images[0];
    setAiLoading(true);
    try {
      const { data } = await api.post("/ai/listing-suggest", { image_url: imageUrl, hints: form.title });
      setForm((f) => ({
        ...f,
        title: data.title || f.title,
        description: data.description || f.description,
        category_id: data.category_id || f.category_id,
        condition: data.condition || f.condition,
        brand: data.brand || f.brand,
        color: data.color || f.color,
        size: data.size || f.size,
        price: data.suggested_price_usd ? String(data.suggested_price_usd) : f.price,
      }));
      toast({ title: "AI regenerated the copy", description: `New title: ${data.title}` });
    } catch (err) {
      toast({ title: "AI regenerate failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setAiLoading(false);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put(`/listings/${id}`, {
        title: form.title.trim(),
        description: form.description.trim(),
        price: parseFloat(form.price),
        original_price: form.original_price ? parseFloat(form.original_price) : null,
        category_id: form.category_id,
        condition: form.condition,
        brand: form.brand.trim() || null,
        size: form.size.trim() || null,
        color: form.color.trim() || null,
        shipping_paid_by: form.shipping_paid_by,
        shipping_method: form.shipping_method,
      });
      toast({ title: "Listing updated" });
      navigate(`/listing/${id}`);
    } catch (err) {
      toast({ title: "Update failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (!listing) return <div className="max-w-4xl mx-auto px-4 py-12 text-neutral-500">Loading…</div>;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8" data-testid="edit-listing-page">
      <h1 className="text-3xl font-bold">Edit listing</h1>
      <p className="text-neutral-500 mt-1">Pick a photo and regenerate the copy with AI, or edit fields manually.</p>

      <div className="mt-6 grid md:grid-cols-[280px_1fr] gap-6">
        {/* Photo picker */}
        <div>
          <Label className="text-sm">Photos</Label>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {(listing.images || []).map((src, i) => (
              <button
                type="button"
                key={i}
                onClick={() => setSelectedPhotoIdx(i)}
                className={`aspect-square rounded-lg overflow-hidden border-2 transition ${i === selectedPhotoIdx ? "border-[#5459E8]" : "border-transparent hover:border-neutral-300"}`}
                data-testid={`edit-photo-${i}`}
              >
                <img src={src} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={regenerate}
            disabled={aiLoading}
            className="mt-3 w-full gap-1.5 border-[#5459E8] text-[#5459E8] hover:bg-[#FFF3F2]"
            data-testid="edit-ai-regenerate-btn"
          >
            <Sparkles className="h-4 w-4" />
            {aiLoading ? "Regenerating…" : "Regenerate copy with AI"}
          </Button>
          <p className="text-xs text-neutral-500 mt-2">Uses the selected photo. Title, description, category, condition &amp; price will be replaced.</p>
        </div>

        {/* Form */}
        <form onSubmit={save} className="space-y-4" data-testid="edit-form">
          <div>
            <Label>Title</Label>
            <Input value={form.title} onChange={set("title")} required className="mt-1" data-testid="edit-title" />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={form.description} onChange={set("description")} rows={5} required className="mt-1" data-testid="edit-description" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Price ($)</Label>
              <Input type="number" step="0.01" min="0" value={form.price} onChange={set("price")} required className="mt-1" data-testid="edit-price" />
            </div>
            <div>
              <Label>Original price ($)</Label>
              <Input type="number" step="0.01" min="0" value={form.original_price} onChange={set("original_price")} className="mt-1" />
            </div>
          </div>
          <div>
            <Label>Category</Label>
            <Select value={form.category_id} onValueChange={set("category_id")}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Condition</Label>
            <RadioGroup value={form.condition} onValueChange={set("condition")} className="mt-2 grid grid-cols-5 gap-2">
              {[["new", "New"], ["like_new", "Like new"], ["good", "Good"], ["fair", "Fair"], ["poor", "Poor"]].map(([v, l]) => (
                <label key={v} className={`border rounded-lg p-2 text-center text-sm cursor-pointer ${form.condition === v ? "border-[#5459E8] bg-[#FFF3F2]" : "border-neutral-200"}`}>
                  <RadioGroupItem value={v} className="sr-only" />{l}
                </label>
              ))}
            </RadioGroup>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Brand</Label><Input value={form.brand} onChange={set("brand")} className="mt-1" /></div>
            <div><Label>Size</Label><Input value={form.size} onChange={set("size")} className="mt-1" /></div>
            <div><Label>Color</Label><Input value={form.color} onChange={set("color")} className="mt-1" /></div>
          </div>
          <Button type="submit" disabled={saving} className="bg-[#DC2626] hover:bg-[#e01d1b] h-11 px-6" data-testid="edit-save-btn">
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </form>
      </div>
    </div>
  );
};

export default EditListing;
