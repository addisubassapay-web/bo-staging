import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Camera, X, Upload, DollarSign } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const PLACEHOLDER_SEEDS = ["seed1", "seed2", "seed3", "seed4", "seed5", "seed6", "seed7", "seed8"];

const Sell = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const [categories, setCategories] = useState([]);
  const [images, setImages] = useState([]);
  const [form, setForm] = useState({
    title: "",
    description: "",
    price: "",
    original_price: "",
    category_id: "",
    condition: "good",
    brand: "",
    size: "",
    color: "",
    shipping_paid_by: "seller",
    shipping_method: "Standard",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) navigate("/login");
    api.get("/categories").then((r) => setCategories(r.data));
  }, [user, authLoading, navigate]);

  const addPlaceholder = () => {
    const seed = PLACEHOLDER_SEEDS[Math.floor(Math.random() * PLACEHOLDER_SEEDS.length)] + Date.now();
    setImages((prev) => [...prev, `https://picsum.photos/seed/${seed}/800/800`]);
  };

  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => setImages((prev) => [...prev, ev.target.result]);
      reader.readAsDataURL(file);
    });
  };

  const removeImage = (idx) => setImages((prev) => prev.filter((_, i) => i !== idx));

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title || !form.description || !form.price || !form.category_id) {
      toast({ title: "Please fill in all required fields", variant: "destructive" });
      return;
    }
    if (images.length === 0) {
      toast({ title: "Add at least one photo", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        price: parseFloat(form.price),
        original_price: form.original_price ? parseFloat(form.original_price) : null,
        images,
      };
      const { data } = await api.post("/listings", payload);
      toast({ title: "Listing published!", description: "Your item is now live." });
      navigate(`/listing/${data.id}`);
    } catch (err) {
      toast({ title: "Could not publish", description: err.response?.data?.detail || "Please try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-neutral-900">Sell an item</h1>
      <p className="text-neutral-600 mt-1">List your item in minutes. Free to list, fees apply on sale.</p>

      <form onSubmit={submit} className="mt-8 space-y-8">
        {/* Photos */}
        <section>
          <Label className="text-base font-semibold">Photos <span className="text-[#FF211F]">*</span></Label>
          <p className="text-sm text-neutral-500 mb-3">Add up to 8 photos. First photo is the cover.</p>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
            {images.map((src, i) => (
              <div key={i} className="relative aspect-square rounded-lg overflow-hidden bg-neutral-100 group">
                <img src={src} alt="" className="w-full h-full object-cover" />
                {i === 0 && <span className="absolute top-1 left-1 bg-[#FF211F] text-white text-[10px] px-1.5 py-0.5 rounded">Cover</span>}
                <button type="button" onClick={() => removeImage(i)} className="absolute top-1 right-1 h-6 w-6 rounded-full bg-black/60 hover:bg-black/80 text-white grid place-items-center">
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            {images.length < 8 && (
              <>
                <label className="aspect-square rounded-lg border-2 border-dashed border-neutral-300 hover:border-[#FF211F] hover:bg-[#FFF3F2] grid place-items-center cursor-pointer transition">
                  <div className="flex flex-col items-center gap-1 text-neutral-500">
                    <Upload className="h-5 w-5" />
                    <span className="text-xs">Upload</span>
                  </div>
                  <input type="file" accept="image/*" multiple className="hidden" onChange={handleFileUpload} />
                </label>
                <button
                  type="button"
                  onClick={addPlaceholder}
                  className="aspect-square rounded-lg border-2 border-dashed border-neutral-300 hover:border-[#FF211F] hover:bg-[#FFF3F2] grid place-items-center transition"
                >
                  <div className="flex flex-col items-center gap-1 text-neutral-500">
                    <Camera className="h-5 w-5" />
                    <span className="text-xs">Add sample</span>
                  </div>
                </button>
              </>
            )}
          </div>
        </section>

        <section className="space-y-4">
          <div>
            <Label>Title <span className="text-[#FF211F]">*</span></Label>
            <Input value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="e.g. Vintage Denim Jacket" maxLength={80} className="mt-1" />
            <div className="text-xs text-neutral-400 mt-1">{form.title.length}/80</div>
          </div>

          <div>
            <Label>Description <span className="text-[#FF211F]">*</span></Label>
            <Textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={4} placeholder="Describe your item, condition, measurements, flaws…" className="mt-1" />
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Category <span className="text-[#FF211F]">*</span></Label>
              <Select value={form.category_id} onValueChange={(v) => set("category_id", v)}>
                <SelectTrigger className="mt-1"><SelectValue placeholder="Select category" /></SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Condition <span className="text-[#FF211F]">*</span></Label>
              <Select value={form.condition} onValueChange={(v) => set("condition", v)}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="new">New with tags</SelectItem>
                  <SelectItem value="like_new">Like new</SelectItem>
                  <SelectItem value="good">Good</SelectItem>
                  <SelectItem value="fair">Fair</SelectItem>
                  <SelectItem value="poor">Poor</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid sm:grid-cols-3 gap-4">
            <div>
              <Label>Brand</Label>
              <Input value={form.brand} onChange={(e) => set("brand", e.target.value)} placeholder="Optional" className="mt-1" />
            </div>
            <div>
              <Label>Size</Label>
              <Input value={form.size} onChange={(e) => set("size", e.target.value)} placeholder="Optional" className="mt-1" />
            </div>
            <div>
              <Label>Color</Label>
              <Input value={form.color} onChange={(e) => set("color", e.target.value)} placeholder="Optional" className="mt-1" />
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Selling price <span className="text-[#FF211F]">*</span></Label>
              <div className="relative mt-1">
                <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
                <Input type="number" step="0.01" value={form.price} onChange={(e) => set("price", e.target.value)} placeholder="0.00" className="pl-8" />
              </div>
            </div>
            <div>
              <Label>Original price</Label>
              <div className="relative mt-1">
                <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
                <Input type="number" step="0.01" value={form.original_price} onChange={(e) => set("original_price", e.target.value)} placeholder="Optional" className="pl-8" />
              </div>
            </div>
          </div>

          <div>
            <Label>Shipping paid by</Label>
            <RadioGroup value={form.shipping_paid_by} onValueChange={(v) => set("shipping_paid_by", v)} className="mt-2 grid sm:grid-cols-2 gap-2">
              <label className={`border rounded-lg p-3 cursor-pointer ${form.shipping_paid_by === "seller" ? "border-[#FF211F] bg-[#FFF3F2]" : "border-neutral-200"}`}>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="seller" />
                  <div>
                    <div className="font-medium text-sm">Seller pays</div>
                    <div className="text-xs text-neutral-500">Free shipping = more sales</div>
                  </div>
                </div>
              </label>
              <label className={`border rounded-lg p-3 cursor-pointer ${form.shipping_paid_by === "buyer" ? "border-[#FF211F] bg-[#FFF3F2]" : "border-neutral-200"}`}>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="buyer" />
                  <div>
                    <div className="font-medium text-sm">Buyer pays</div>
                    <div className="text-xs text-neutral-500">Calculated at checkout</div>
                  </div>
                </div>
              </label>
            </RadioGroup>
          </div>
        </section>

        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
          <Button type="submit" disabled={submitting} className="bg-[#FF211F] hover:bg-[#e01d1b] min-w-[140px]">
            {submitting ? "Publishing…" : "Publish listing"}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default Sell;
