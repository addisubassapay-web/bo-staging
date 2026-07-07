import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Store as StoreIcon, ExternalLink, Save } from "lucide-react";

const StoreManage = () => {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [existing, setExisting] = useState(null);
  const [pageLoading, setPageLoading] = useState(true);
  const [form, setForm] = useState({ name: "", slug: "", tagline: "", bio: "", logo: "", banner: "" });
  const [saving, setSaving] = useState(false);

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
        });
      }
    }).finally(() => setPageLoading(false));
  }, [user, loading, navigate]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSlug = (v) => set("slug", v.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-"));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.slug) { toast({ title: "Name and slug are required", variant: "destructive" }); return; }
    setSaving(true);
    try {
      if (existing) {
        const { data } = await api.put(`/stores/${existing.id}`, {
          name: form.name, tagline: form.tagline, bio: form.bio, logo: form.logo || null, banner: form.banner || null,
        });
        setExisting(data);
        toast({ title: "Store updated" });
      } else {
        const { data } = await api.post("/stores", form);
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
          <StoreIcon className="h-6 w-6 text-[#FF211F]" />
          <h1 className="text-3xl font-bold">{existing ? "Manage your store" : "Create a store"}</h1>
        </div>
        {existing && (
          <Link to={`/store/${existing.slug}`}>
            <Button variant="outline" size="sm"><ExternalLink className="h-4 w-4 mr-1" /> View public page</Button>
          </Link>
        )}
      </div>
      <p className="text-neutral-600 mb-6">Your storefront is your brand. Give it a memorable name and a public URL.</p>

      <form onSubmit={submit} className="space-y-5">
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <Label>Store name</Label>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Sophia&apos;s Style" className="mt-1" required />
          </div>
          <div>
            <Label>URL slug</Label>
            <div className="mt-1 flex items-center gap-1">
              <span className="text-sm text-neutral-500">/store/</span>
              <Input value={form.slug} onChange={(e) => handleSlug(e.target.value)} placeholder="sophias-style" required disabled={!!existing} />
            </div>
            {existing && <div className="text-xs text-neutral-400 mt-1">Slug can&apos;t be changed after creation.</div>}
          </div>
        </div>
        <div>
          <Label>Tagline</Label>
          <Input value={form.tagline} onChange={(e) => set("tagline", e.target.value)} placeholder="e.g. Curated fashion at a fair price" className="mt-1" maxLength={100} />
        </div>
        <div>
          <Label>About your store</Label>
          <Textarea rows={4} value={form.bio} onChange={(e) => set("bio", e.target.value)} placeholder="Tell shoppers what makes your store special…" className="mt-1" />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <Label>Logo URL</Label>
            <Input value={form.logo} onChange={(e) => set("logo", e.target.value)} placeholder="https://… (optional)" className="mt-1" />
          </div>
          <div>
            <Label>Banner URL</Label>
            <Input value={form.banner} onChange={(e) => set("banner", e.target.value)} placeholder="https://… (optional)" className="mt-1" />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-[#FF211F] hover:bg-[#e01d1b]">
            <Save className="h-4 w-4 mr-1" /> {saving ? "Saving…" : (existing ? "Save changes" : "Create store")}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default StoreManage;
