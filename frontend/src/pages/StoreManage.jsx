import React, { useEffect, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Store as StoreIcon, ExternalLink, Save, Tag, Upload, Loader2, Image as ImageIcon, Globe, Mail, MapPin, Trash2 } from "lucide-react";
import { COUNTRIES, flagEmoji, countryName } from "@/constants/countries";

const MAX_STORE_CATEGORIES = 3;

const StoreManage = () => {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [existing, setExisting] = useState(null);
  const [pageLoading, setPageLoading] = useState(true);
  const [form, setForm] = useState({
    name: "", slug: "", tagline: "", bio: "", logo: "", banner: "",
    country: "", contact_email: "", website: "",
    category_ids: [],
  });
  const [saving, setSaving] = useState(false);
  const [categories, setCategories] = useState([]);
  const [uploading, setUploading] = useState({ logo: false, banner: false });
  const logoInputRef = useRef(null);
  const bannerInputRef = useRef(null);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/my/store").then((r) => {
      if (r.data) {
        setExisting(r.data);
        setForm({
          name: r.data.name || "",
          slug: r.data.slug || "",
          tagline: r.data.tagline || "",
          bio: r.data.bio || "",
          logo: r.data.logo || "",
          banner: r.data.banner || "",
          country: r.data.country || "",
          contact_email: r.data.contact_email || "",
          website: r.data.website || "",
          category_ids: r.data.category_ids || [],
        });
      }
    }).finally(() => setPageLoading(false));
  }, [user, loading, navigate]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSlug = (v) => set("slug", v.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-"));

  const toggleCategory = (id) => {
    setForm((f) => {
      const has = f.category_ids.includes(id);
      if (has) return { ...f, category_ids: f.category_ids.filter((c) => c !== id) };
      if (f.category_ids.length >= MAX_STORE_CATEGORIES) {
        toast({ title: `Pick at most ${MAX_STORE_CATEGORIES} categories`, variant: "destructive" });
        return f;
      }
      return { ...f, category_ids: [...f.category_ids, id] };
    });
  };

  const uploadImage = async (file, kind) => {
    if (!file) return;
    if (!/^image\//.test(file.type || "")) {
      toast({ title: "Choose an image file", variant: "destructive" });
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      toast({ title: "Image too large", description: "Max 12 MB", variant: "destructive" });
      return;
    }
    setUploading((u) => ({ ...u, [kind]: true }));
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", kind === "logo" ? "store-logo" : "store-banner");
      const { data } = await api.post("/upload/public-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
      if (!data?.url) throw new Error("No URL returned");
      set(kind, data.url);
      toast({ title: `${kind === "logo" ? "Logo" : "Cover"} uploaded` });
    } catch (e) {
      toast({ title: "Upload failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setUploading((u) => ({ ...u, [kind]: false }));
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.slug) { toast({ title: "Name and slug are required", variant: "destructive" }); return; }
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        tagline: form.tagline,
        bio: form.bio,
        logo: form.logo || null,
        banner: form.banner || null,
        country: form.country || null,
        contact_email: form.contact_email || null,
        website: form.website || null,
        category_ids: form.category_ids,
      };
      if (existing) {
        const { data } = await api.put(`/stores/${existing.id}`, payload);
        setExisting(data);
        toast({ title: "Store updated" });
      } else {
        const { data } = await api.post("/stores", { ...payload, slug: form.slug });
        setExisting(data);
        await refresh();
        toast({ title: "Store created!", description: "Your store is live." });
      }
    } catch (err) {
      toast({ title: "Failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (pageLoading) return <div className="max-w-3xl mx-auto px-4 py-8">Loading…</div>;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <StoreIcon className="h-6 w-6 text-[#DC2626]" />
          <h1 className="text-3xl font-bold">{existing ? "Manage your store" : "Create a store"}</h1>
        </div>
        {existing && (
          <Link to={`/store/${existing.slug}`}>
            <Button variant="outline" size="sm" data-testid="store-view-public-btn"><ExternalLink className="h-4 w-4 mr-1" /> View public page</Button>
          </Link>
        )}
      </div>
      <p className="text-neutral-600 mb-6">Your storefront is your brand. Add a cover image, logo, and country so shoppers know exactly who they&apos;re buying from.</p>

      <form onSubmit={submit} className="space-y-6">
        {/* Cover / Banner uploader */}
        <div>
          <Label className="flex items-center gap-1.5"><ImageIcon className="h-4 w-4 text-[#5459E8]" /> Cover image</Label>
          <p className="text-xs text-neutral-500 mt-0.5 mb-2">Wide banner shown at the top of your storefront (recommended 1600×400).</p>
          <div className="relative rounded-xl border-2 border-dashed border-neutral-300 dark:border-neutral-700 overflow-hidden bg-neutral-50 dark:bg-neutral-900 aspect-[4/1] group" data-testid="store-banner-uploader">
            {form.banner ? (
              <>
                <img src={form.banner} alt="cover" className="absolute inset-0 h-full w-full object-cover" />
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity grid place-items-center gap-2">
                  <Button type="button" variant="secondary" size="sm" onClick={() => bannerInputRef.current?.click()} data-testid="store-banner-replace">
                    <Upload className="h-4 w-4 mr-1" /> Replace
                  </Button>
                  <Button type="button" variant="destructive" size="sm" onClick={() => set("banner", "")} data-testid="store-banner-remove">
                    <Trash2 className="h-4 w-4 mr-1" /> Remove
                  </Button>
                </div>
              </>
            ) : (
              <button
                type="button"
                onClick={() => bannerInputRef.current?.click()}
                className="absolute inset-0 grid place-items-center text-neutral-500 hover:text-[#DC2626] hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                data-testid="store-banner-upload"
              >
                {uploading.banner ? <Loader2 className="h-8 w-8 animate-spin" /> : (
                  <div className="text-center">
                    <Upload className="h-8 w-8 mx-auto mb-1" />
                    <div className="text-sm font-medium">Upload cover image</div>
                    <div className="text-xs text-neutral-400">PNG · JPG · WEBP up to 12 MB</div>
                  </div>
                )}
              </button>
            )}
            <input ref={bannerInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0], "banner")} />
          </div>
          <Input value={form.banner} onChange={(e) => set("banner", e.target.value)} placeholder="or paste banner URL" className="mt-2 text-xs" data-testid="store-banner-url" />
        </div>

        {/* Logo uploader + basics */}
        <div className="grid sm:grid-cols-[160px_1fr] gap-5 items-start">
          <div>
            <Label className="flex items-center gap-1.5"><ImageIcon className="h-4 w-4 text-[#7C3AED]" /> Profile picture</Label>
            <p className="text-xs text-neutral-500 mt-0.5 mb-2">Square logo.</p>
            <div className="relative rounded-2xl border-2 border-dashed border-neutral-300 dark:border-neutral-700 overflow-hidden bg-white dark:bg-neutral-900 aspect-square group" data-testid="store-logo-uploader">
              {form.logo ? (
                <>
                  <img src={form.logo} alt="logo" className="absolute inset-0 h-full w-full object-cover" />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity grid place-items-center gap-1.5">
                    <Button type="button" variant="secondary" size="sm" onClick={() => logoInputRef.current?.click()} data-testid="store-logo-replace">
                      <Upload className="h-3.5 w-3.5 mr-1" /> Replace
                    </Button>
                    <Button type="button" variant="destructive" size="sm" onClick={() => set("logo", "")} data-testid="store-logo-remove">
                      <Trash2 className="h-3.5 w-3.5 mr-1" /> Remove
                    </Button>
                  </div>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => logoInputRef.current?.click()}
                  className="absolute inset-0 grid place-items-center text-neutral-500 hover:text-[#DC2626] hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                  data-testid="store-logo-upload"
                >
                  {uploading.logo ? <Loader2 className="h-7 w-7 animate-spin" /> : (
                    <div className="text-center px-1">
                      <Upload className="h-6 w-6 mx-auto mb-0.5" />
                      <div className="text-[11px] font-medium leading-tight">Upload<br />photo</div>
                    </div>
                  )}
                </button>
              )}
              <input ref={logoInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0], "logo")} />
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <Label>Store name</Label>
              <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Sophia&apos;s Style" className="mt-1" required data-testid="store-name-input" />
            </div>
            <div>
              <Label>URL slug</Label>
              <div className="mt-1 flex items-center gap-1">
                <span className="text-sm text-neutral-500">/store/</span>
                <Input value={form.slug} onChange={(e) => handleSlug(e.target.value)} placeholder="sophias-style" required disabled={!!existing} data-testid="store-slug-input" />
              </div>
              {existing && <div className="text-xs text-neutral-400 mt-1">Slug can&apos;t be changed after creation.</div>}
            </div>
            <div>
              <Label>Tagline</Label>
              <Input value={form.tagline} onChange={(e) => set("tagline", e.target.value)} placeholder="e.g. Curated fashion at a fair price" className="mt-1" maxLength={100} data-testid="store-tagline-input" />
            </div>
          </div>
        </div>

        <div>
          <Label>About your store</Label>
          <Textarea rows={4} value={form.bio} onChange={(e) => set("bio", e.target.value)} placeholder="Tell shoppers what makes your store special…" className="mt-1" data-testid="store-bio-input" />
        </div>

        {/* Country picker w/ live flag */}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <Label className="flex items-center gap-1.5"><MapPin className="h-4 w-4 text-[#059669]" /> Country / region</Label>
            <p className="text-xs text-neutral-500 mt-0.5 mb-2">Shown as a flag pill on your storefront.</p>
            <Select value={form.country || "none"} onValueChange={(v) => set("country", v === "none" ? "" : v)}>
              <SelectTrigger data-testid="store-country-select">
                <SelectValue placeholder="Choose a country">
                  {form.country ? (
                    <span className="inline-flex items-center gap-2"><span className="text-lg leading-none" data-testid="store-country-flag-preview">{flagEmoji(form.country)}</span> {countryName(form.country)}</span>
                  ) : (
                    <span className="text-neutral-500">Choose a country</span>
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent className="max-h-80">
                <SelectItem value="none">— No country —</SelectItem>
                {COUNTRIES.map((c) => (
                  <SelectItem key={c.code} value={c.code} data-testid={`store-country-opt-${c.code}`}>
                    <span className="inline-flex items-center gap-2"><span className="text-lg leading-none">{flagEmoji(c.code)}</span> {c.name}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="flex items-center gap-1.5"><Mail className="h-4 w-4 text-[#2563EB]" /> Contact email</Label>
            <p className="text-xs text-neutral-500 mt-0.5 mb-2">Optional — shown to buyers on your storefront.</p>
            <Input type="email" value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} placeholder="hello@yourbrand.com" data-testid="store-contact-email" />
          </div>
        </div>

        <div>
          <Label className="flex items-center gap-1.5"><Globe className="h-4 w-4 text-[#0EA5E9]" /> Website</Label>
          <Input value={form.website} onChange={(e) => set("website", e.target.value)} placeholder="https://yourbrand.com" className="mt-1" data-testid="store-website" />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-2">
            <Tag className="h-4 w-4 text-[#2563EB]" />
            <Label className="!mb-0">Store categories</Label>
            <span className="text-xs text-neutral-400">
              ({form.category_ids.length}/{MAX_STORE_CATEGORIES} selected)
            </span>
          </div>
          <p className="text-xs text-neutral-500 mb-3">Pick up to 3 categories that best describe what you sell. Shoppers use these to filter the store directory.</p>
          <div className="flex flex-wrap gap-2" data-testid="store-categories-picker">
            {categories.map((c) => {
              const selected = form.category_ids.includes(c.id);
              const disabled = !selected && form.category_ids.length >= MAX_STORE_CATEGORIES;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggleCategory(c.id)}
                  disabled={disabled}
                  data-testid={`store-cat-${c.slug}`}
                  aria-pressed={selected}
                  className={`px-3 h-8 rounded-full text-xs font-semibold transition border ${
                    selected
                      ? "bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white border-transparent shadow-sm"
                      : disabled
                        ? "bg-neutral-50 text-neutral-300 border-neutral-100 cursor-not-allowed dark:bg-neutral-900 dark:text-neutral-600 dark:border-neutral-800"
                        : "bg-white text-neutral-700 border-neutral-200 hover:border-[#2563EB] hover:text-[#2563EB] dark:bg-neutral-900 dark:text-neutral-200 dark:border-neutral-700"
                  }`}
                >
                  {c.name}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-[#DC2626] hover:bg-[#e01d1b]" data-testid="store-save-btn">
            <Save className="h-4 w-4 mr-1" /> {saving ? "Saving…" : (existing ? "Save changes" : "Create store")}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default StoreManage;
