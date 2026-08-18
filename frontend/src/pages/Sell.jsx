import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Camera, X, Upload, DollarSign, Sparkles, Wand2, PackagePlus, PenLine, Lock, ShieldCheck, Clock as ClockIcon, Link as LinkIcon } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import ResellFromCatalog from "@/components/ResellFromCatalog";
import ImportFromUrl from "@/components/ImportFromUrl";
import BulkImportFromUrls from "@/components/BulkImportFromUrls";
import CategoryScrapeAtScale from "@/components/CategoryScrapeAtScale";
import { Link } from "react-router-dom";

const PLACEHOLDER_SEEDS = ["seed1", "seed2", "seed3", "seed4", "seed5", "seed6", "seed7", "seed8"];

const SellerGate = ({ status }) => {
  const cases = {
    none: {
      icon: Lock, color: "bg-[#FFF3F2] text-[#FF211F]", title: "Selling is limited to verified sellers",
      body: "Take 2 minutes to submit your seller application. Once an admin approves you, listing (new items) and reselling (catalog items) both unlock instantly.",
      cta: { to: "/seller/apply", label: "Apply to sell", primary: true },
    },
    pending: {
      icon: ClockIcon, color: "bg-amber-100 text-amber-700",
      title: "Application under review",
      body: "Your seller application is with the admin team. You'll get a notification the moment you're approved and this page will unlock.",
      cta: { to: "/seller/apply", label: "View my application", primary: false },
    },
    rejected: {
      icon: Lock, color: "bg-red-100 text-red-700",
      title: "Application not approved",
      body: "Please review the admin's notes and reapply with the requested changes to unlock selling and reselling.",
      cta: { to: "/seller/apply", label: "Update & resubmit", primary: true },
    },
  };
  const c = cases[status] || cases.none;
  const Icon = c.icon;
  return (
    <div className="mt-6 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 sm:p-8 text-center" data-testid={`seller-gate-${status || "none"}`}>
      <div className={`h-14 w-14 rounded-full mx-auto grid place-items-center ${c.color}`}><Icon className="h-6 w-6" /></div>
      <h2 className="mt-4 text-xl sm:text-2xl font-bold text-neutral-900 dark:text-neutral-100">{c.title}</h2>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300 max-w-md mx-auto">{c.body}</p>
      <ul className="mt-5 grid gap-2 text-sm text-neutral-600 dark:text-neutral-300 max-w-md mx-auto text-left">
        <li className="flex items-start gap-2"><ShieldCheck className="h-4 w-4 mt-0.5 text-emerald-600 shrink-0" /> Publish your own items with instant photos + AI descriptions</li>
        <li className="flex items-start gap-2"><ShieldCheck className="h-4 w-4 mt-0.5 text-emerald-600 shrink-0" /> Resell any catalog product to your storefront with tier-based wholesale discounts</li>
        <li className="flex items-start gap-2"><ShieldCheck className="h-4 w-4 mt-0.5 text-emerald-600 shrink-0" /> Bulk publish up to 20 items at once</li>
      </ul>
      <Link to={c.cta.to}>
        <Button
          className={`min-h-[48px] rounded-full mt-6 px-6 gap-1.5 ${c.cta.primary ? "bg-[#FF211F] hover:bg-[#e01d1b] text-white" : "bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-neutral-100 hover:bg-neutral-200"}`}
          data-testid="seller-gate-cta"
        >
          {c.cta.label}
        </Button>
      </Link>
    </div>
  );
};

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
  const [aiLoading, setAiLoading] = useState(false);
  const [enhancingIdx, setEnhancingIdx] = useState(-1);
  const [enhanceAllBusy, setEnhanceAllBusy] = useState(false);
  const [prePublishOpen, setPrePublishOpen] = useState(false);
  const [mode, setMode] = useState("new"); // "new" | "resell" | "import"

  const applyImport = (listing /* , job */) => {
    setForm((prev) => ({
      ...prev,
      title: listing?.title || prev.title,
      description: listing?.description || prev.description,
      price: listing?.price ? String(listing.price) : prev.price,
      brand: listing?.brand || prev.brand,
    }));
    if (Array.isArray(listing?.images) && listing.images.length > 0) {
      setImages(listing.images.slice(0, 8));
    }
    setMode("new");
    toast({ title: "Prefilled from URL", description: "Review the details and publish when ready." });
  };

  const enhanceAll = async () => {
    if (images.length === 0) return;
    setEnhanceAllBusy(true);
    const token = localStorage.getItem("mercari_token");
    const nextImages = [...images];
    for (let i = 0; i < nextImages.length; i++) {
      const src = nextImages[i];
      try {
        const body = src.startsWith("data:") ? { image_base64: src } : { image_url: src };
        const { data } = await api.post("/ai/photo-enhance", body);
        nextImages[i] = `${process.env.REACT_APP_BACKEND_URL}${data.url}?auth=${encodeURIComponent(token || "")}`;
        setImages([...nextImages]);
      } catch {
        // keep original if enhancement fails
      }
    }
    setEnhanceAllBusy(false);
    toast({ title: "All photos enhanced", description: "Your listing is grid-ready." });
  };

  const enhancePhoto = async (idx) => {
    const src = images[idx];
    if (!src) return;
    setEnhancingIdx(idx);
    try {
      const body = src.startsWith("data:") ? { image_base64: src } : { image_url: src };
      const { data } = await api.post("/ai/photo-enhance", body);
      // Use the enhanced URL directly — replace the photo at the same index
      const token = localStorage.getItem("mercari_token");
      const enhancedUrl = `${process.env.REACT_APP_BACKEND_URL}${data.url}?auth=${encodeURIComponent(token || "")}`;
      setImages((prev) => prev.map((v, i) => (i === idx ? enhancedUrl : v)));
      toast({ title: "Photo enhanced", description: "Background removed & polished by AI" });
    } catch (err) {
      toast({ title: "Enhance failed", description: err.response?.data?.detail || "Try a different photo", variant: "destructive" });
    } finally {
      setEnhancingIdx(-1);
    }
  };

  const runAiFromImage = async (dataUrl) => {
    setAiLoading(true);
    try {
      const { data } = await api.post("/ai/listing-suggest", { image_base64: dataUrl, hints: form.title || "" });
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
        original_price: data.original_price_usd ? String(data.original_price_usd) : f.original_price,
      }));
      toast({ title: "AI filled the listing", description: `Suggested price: $${data.suggested_price_usd || "—"}` });
    } catch (err) {
      toast({ title: "AI suggestion failed", description: err.response?.data?.detail || "Try a clearer photo", variant: "destructive" });
    } finally {
      setAiLoading(false);
    }
  };

  const suggestFromFirstPhoto = async () => {
    if (images.length === 0) {
      toast({ title: "Add a photo first", variant: "destructive" });
      return;
    }
    const first = images[0];
    // If it's already a data URL / base64 → send as-is; if it's a URL → send as image_url
    if (first.startsWith("data:")) {
      await runAiFromImage(first);
    } else {
      setAiLoading(true);
      try {
        const { data } = await api.post("/ai/listing-suggest", { image_url: first, hints: form.title || "" });
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
          original_price: data.original_price_usd ? String(data.original_price_usd) : f.original_price,
        }));
        toast({ title: "AI filled the listing" });
      } catch (err) {
        toast({ title: "AI suggestion failed", description: err.response?.data?.detail || "Try a clearer photo", variant: "destructive" });
      } finally {
        setAiLoading(false);
      }
    }
  };

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/categories").then((r) => setCategories(r.data));
  }, [user, authLoading, navigate]);

  const isApprovedSeller = user && (user.role === "admin" || user.seller_status === "approved");

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
    // Check if any photo is un-enhanced (not from AI /files endpoint). If so, prompt.
    const anyRaw = images.some((src) => !src.includes("/api/files/"));
    if (anyRaw && !prePublishOpen) {
      setPrePublishOpen(true);
      return;
    }
    setPrePublishOpen(false);
    await doPublish();
  };

  const doPublish = async () => {
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
      <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Sell an item</h1>
      <p className="text-neutral-600 dark:text-neutral-400 mt-1">List your item in minutes. Free to list, fees apply on sale.</p>

      {!isApprovedSeller ? (
        <SellerGate status={user?.seller_status} />
      ) : (
      <>
      {/* Mode toggle: new listing vs resell existing vs import from URL */}
      <div className="mt-6 grid grid-cols-3 gap-2 p-1 rounded-full bg-neutral-100 dark:bg-neutral-800 max-w-2xl" data-testid="sell-mode-toggle">
        <button
          type="button"
          onClick={() => setMode("new")}
          className={`h-10 rounded-full text-sm font-semibold transition inline-flex items-center justify-center gap-1.5 ${mode === "new" ? "bg-white dark:bg-neutral-950 text-[#FF211F] shadow-sm" : "text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"}`}
          data-testid="sell-mode-new"
        >
          <PenLine className="h-4 w-4" /> New listing
        </button>
        <button
          type="button"
          onClick={() => setMode("resell")}
          className={`h-10 rounded-full text-sm font-semibold transition inline-flex items-center justify-center gap-1.5 ${mode === "resell" ? "bg-white dark:bg-neutral-950 text-[#FF211F] shadow-sm" : "text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"}`}
          data-testid="sell-mode-resell"
        >
          <PackagePlus className="h-4 w-4" /> Resell existing
        </button>
        <button
          type="button"
          onClick={() => setMode("import")}
          className={`h-10 rounded-full text-sm font-semibold transition inline-flex items-center justify-center gap-1.5 ${mode === "import" ? "bg-white dark:bg-neutral-950 text-[#FF211F] shadow-sm" : "text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"}`}
          data-testid="sell-mode-import"
        >
          <LinkIcon className="h-4 w-4" /> Import from URL
        </button>
      </div>

      {mode === "resell" ? (
        <ResellFromCatalog />
      ) : mode === "import" ? (
        <div className="mt-8 space-y-6">
          <CategoryScrapeAtScale />
          <ImportFromUrl onImportReady={applyImport} />
          <BulkImportFromUrls onUseListing={applyImport} />
        </div>
      ) : (
      <form onSubmit={submit} className="mt-8 space-y-8">
        {/* Photos */}
        <section>
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base font-semibold">Photos <span className="text-[#FF211F]">*</span></Label>
              <p className="text-sm text-neutral-500 mb-1">Add up to 8 photos. First photo is the cover.</p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={suggestFromFirstPhoto}
              disabled={aiLoading || images.length === 0}
              className="gap-1.5 border-[#FF211F] text-[#FF211F] hover:bg-[#FFF3F2]"
              data-testid="ai-suggest-btn"
            >
              <Sparkles className="h-4 w-4" />
              {aiLoading ? "Analyzing…" : "AI-fill from photo"}
            </Button>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 mt-3">
            {images.map((src, i) => (
              <div key={i} className="relative aspect-square rounded-lg overflow-hidden bg-neutral-100 group">
                <img src={src} alt="" className="w-full h-full object-cover" />
                {i === 0 && <span className="absolute top-1 left-1 bg-[#FF211F] text-white text-[10px] px-1.5 py-0.5 rounded">Cover</span>}
                <button
                  type="button"
                  onClick={() => enhancePhoto(i)}
                  disabled={enhancingIdx === i}
                  aria-label="Enhance photo with AI"
                  className="absolute bottom-1 left-1 h-7 w-7 rounded-full bg-[#FF7A18] hover:bg-[#e86a10] disabled:opacity-60 text-white grid place-items-center shadow-md"
                  data-testid={`enhance-photo-${i}`}
                  title="Enhance with AI (Nano Banana)"
                >
                  <Wand2 className={`h-3.5 w-3.5 ${enhancingIdx === i ? "animate-pulse" : ""}`} />
                </button>
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
          <Button type="submit" disabled={submitting} className="bg-[#FF211F] hover:bg-[#e01d1b] min-w-[140px]" data-testid="publish-btn">
            {submitting ? "Publishing…" : "Publish listing"}
          </Button>
        </div>
      </form>
      )}

      {/* Pre-publish enhance prompt */}
      {prePublishOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center px-4" onClick={() => !enhanceAllBusy && setPrePublishOpen(false)} data-testid="pre-publish-modal">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start gap-3">
              <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] grid place-items-center text-white">
                <Sparkles className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold">Make your photos pop?</h3>
                <p className="text-sm text-neutral-600 mt-1">
                  Enhance all photos with AI in one tap — background removed, studio polish, so your listing shines on the grid.
                </p>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-2 mt-4">
              {images.slice(0, 4).map((src, i) => (
                <img key={i} src={src} alt="" className="aspect-square rounded-lg object-cover bg-neutral-100" />
              ))}
            </div>
            <div className="flex gap-2 mt-6">
              <Button
                variant="outline"
                className="flex-1"
                disabled={enhanceAllBusy}
                onClick={() => { setPrePublishOpen(false); doPublish(); }}
                data-testid="publish-skip-enhance"
              >
                Skip &amp; publish
              </Button>
              <Button
                className="flex-1 bg-[#FF7A18] hover:bg-[#e86a10] gap-1.5"
                disabled={enhanceAllBusy}
                onClick={async () => { await enhanceAll(); await doPublish(); }}
                data-testid="publish-enhance-all"
              >
                <Wand2 className={`h-4 w-4 ${enhanceAllBusy ? "animate-pulse" : ""}`} />
                {enhanceAllBusy ? "Enhancing…" : "Enhance all"}
              </Button>
            </div>
          </div>
        </div>
      )}
      </>
      )}
    </div>
  );
};

export default Sell;
