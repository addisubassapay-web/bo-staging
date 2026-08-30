import React, { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import { Loader2, ArrowRight, CheckCircle2, XCircle, Clock, Sparkles, FolderTree, Rocket, Upload, ImageOff } from "lucide-react";

const STATUS_META = {
  queued:  { label: "Queued",   cls: "bg-neutral-100 text-neutral-700",   Icon: Clock },
  running: { label: "Running",  cls: "bg-sky-100 text-sky-700",           Icon: Loader2 },
  done:    { label: "Done",     cls: "bg-emerald-100 text-emerald-700",   Icon: CheckCircle2 },
  failed:  { label: "Failed",   cls: "bg-red-100 text-red-700",           Icon: XCircle },
};

const CategoryScrapeAtScale = () => {
  const { toast } = useToast();
  const [tab, setTab] = useState("category");
  const [categories, setCategories] = useState([]);
  const [categoryUrl, setCategoryUrl] = useState("");
  const [csvText, setCsvText] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [autoPublish, setAutoPublish] = useState(true);
  const [highFidelity, setHighFidelity] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [batchId, setBatchId] = useState(null);
  const [batchState, setBatchState] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const { data } = await api.get(`/scraper/batches/${batchId}`);
        if (cancelled) return;
        setBatchState(data);
        const status = data.batch?.status;
        const active = (data.counts?.queued || 0) + (data.counts?.running || 0);
        if (active === 0 && status !== "queued" && status !== "running") {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
      } catch { /* ignore */ }
    };
    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => { cancelled = true; if (pollRef.current) clearInterval(pollRef.current); };
  }, [batchId]);

  const csvUrls = useMemo(
    () => csvText.split(/[\r\n,]/).map((s) => s.trim()).filter((s) => s.startsWith("http")),
    [csvText],
  );

  const submit = async () => {
    if (autoPublish && !categoryId) {
      toast({ title: "Pick a category first", description: "Auto-publish needs a category.", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    setBatchState(null);
    try {
      let res;
      if (tab === "category") {
        if (!categoryUrl.match(/^https?:\/\//i)) {
          toast({ title: "Enter a valid category / search URL", variant: "destructive" });
          setSubmitting(false); return;
        }
        res = await api.post("/scraper/jobs/category", {
          url: categoryUrl,
          category_id: categoryId || null,
          auto_publish: autoPublish,
          high_fidelity: highFidelity,
        });
      } else {
        if (csvUrls.length === 0) {
          toast({ title: "Paste at least 1 URL", variant: "destructive" });
          setSubmitting(false); return;
        }
        res = await api.post("/scraper/jobs/csv", {
          urls: csvUrls.slice(0, 1000),
          category_id: categoryId || null,
          auto_publish: autoPublish,
          high_fidelity: highFidelity,
        });
      }
      setBatchId(res.data.batch_id);
      toast({
        title: tab === "category" ? "Scraping category page…" : `Queued ${res.data.queued_count} of ${csvUrls.length}`,
        description: autoPublish ? "Products will publish live under your selected category." : "You'll review each before publishing.",
      });
    } catch (e) {
      toast({
        title: "Import failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setSubmitting(false); }
  };

  const reset = () => { setBatchId(null); setBatchState(null); setCategoryUrl(""); setCsvText(""); };

  const jobs = batchState?.jobs || [];
  const published = jobs.filter((j) => j.publish_status === "published").length;
  const total = batchState?.total || 0;
  const doneCount = batchState?.counts?.done || 0;
  const failedCount = batchState?.counts?.failed || 0;
  const progressPct = total ? Math.round(((doneCount + failedCount) / total) * 100) : 0;

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6" data-testid="scale-import-panel">
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 text-white grid place-items-center shrink-0">
          <Rocket className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold">Import at scale</h3>
          <p className="text-sm text-neutral-600 mt-1">
            Point at a category / search page (one Zyte call → up to 100 products) or paste a CSV / spreadsheet (up to 1,000 URLs). Toggle Auto-Publish and they go live under your chosen category the moment extraction finishes.
          </p>
        </div>
      </div>

      {!batchId && (
        <div className="mt-5 space-y-4">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="grid grid-cols-2 max-w-sm">
              <TabsTrigger value="category" data-testid="scale-tab-category"><FolderTree className="h-3.5 w-3.5 mr-1.5" /> Category URL</TabsTrigger>
              <TabsTrigger value="csv" data-testid="scale-tab-csv"><Upload className="h-3.5 w-3.5 mr-1.5" /> CSV paste</TabsTrigger>
            </TabsList>

            <TabsContent value="category" className="mt-4 space-y-3">
              <div>
                <Label className="text-sm">Category or search URL</Label>
                <Input
                  value={categoryUrl}
                  onChange={(e) => setCategoryUrl(e.target.value)}
                  placeholder="https://www.amazon.com/s?k=headphones"
                  className="mt-1 h-10 font-mono text-xs"
                  data-testid="scale-category-url"
                />
                <div className="text-xs text-neutral-500 mt-1">Amazon search, eBay category, Shopify collection, Walmart list — Zyte auto-detects and fans out into individual products.</div>
              </div>
            </TabsContent>

            <TabsContent value="csv" className="mt-4 space-y-3">
              <div>
                <Label className="text-sm">Paste URLs (one per line or comma-separated)</Label>
                <Textarea
                  value={csvText}
                  onChange={(e) => setCsvText(e.target.value)}
                  placeholder="https://www.amazon.com/dp/…&#10;https://www.walmart.com/ip/…&#10;…"
                  rows={7}
                  className="mt-1 font-mono text-xs"
                  data-testid="scale-csv-textarea"
                />
                <div className="text-xs text-neutral-500 mt-1">{csvUrls.length} URLs detected (max 1,000 per submit).</div>
              </div>
            </TabsContent>
          </Tabs>

          {/* Shared controls */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Target category {autoPublish && <span className="text-[#DC2626]">*</span>}</Label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger className="mt-1 h-10" data-testid="scale-category-select">
                  <SelectValue placeholder="Choose a category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <label className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-emerald-300 cursor-pointer transition-colors">
                <Switch checked={autoPublish} onCheckedChange={setAutoPublish} data-testid="scale-autopublish" />
                <div>
                  <div className="text-sm font-semibold flex items-center gap-1.5"><Rocket className="h-3.5 w-3.5 text-emerald-600" /> Auto-publish live</div>
                  <div className="text-xs text-neutral-500 mt-0.5">Skip the review form — every extracted product becomes a live listing immediately.</div>
                </div>
              </label>
              <label className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-amber-300 cursor-pointer transition-colors">
                <Switch checked={highFidelity} onCheckedChange={setHighFidelity} data-testid="scale-hifi" />
                <div>
                  <div className="text-sm font-semibold flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-amber-500" /> Amazon Full Pull</div>
                  <div className="text-xs text-neutral-500 mt-0.5">Force browser rendering + anti-bot proxy. Costs more Zyte credits.</div>
                </div>
              </label>
            </div>
          </div>

          <Button
            onClick={submit}
            disabled={submitting}
            className="w-full sm:w-auto bg-[#DC2626] hover:bg-[#e01d1b] h-11"
            data-testid="scale-import-submit"
          >
            {submitting
              ? (<><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Queueing…</>)
              : (<>Start import <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
          </Button>
        </div>
      )}

      {batchId && (
        <div className="mt-5 space-y-4">
          <div className="rounded-xl border border-neutral-200 bg-neutral-50/50 p-4">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <div className="text-sm font-semibold">
                Batch progress {batchState?.batch?.status && (
                  <Badge variant="secondary" className="ml-2 text-[10px] uppercase">{batchState.batch.status}</Badge>
                )}
              </div>
              <div className="flex items-center gap-1.5 text-xs">
                <Badge className="bg-emerald-100 text-emerald-700 border-none">{doneCount} extracted</Badge>
                {autoPublish && <Badge className="bg-teal-100 text-teal-700 border-none">{published} live</Badge>}
                {failedCount > 0 && <Badge variant="destructive">{failedCount} failed</Badge>}
              </div>
            </div>
            <Progress value={progressPct} className="h-2" />
            <div className="text-xs text-neutral-500 mt-2">{progressPct}% • {total} product{total === 1 ? "" : "s"}</div>
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {jobs.slice(0, 100).map((j) => {
              const meta = STATUS_META[j.status] || STATUS_META.queued;
              const StatusIcon = meta.Icon;
              const listing = j.result?.listing || {};
              return (
                <div key={j.id} className="flex items-center gap-3 p-2.5 rounded-lg border border-neutral-100" data-testid={`scale-job-${j.id.slice(0,8)}`}>
                  <div className="h-10 w-10 rounded bg-neutral-100 grid place-items-center overflow-hidden shrink-0">
                    {listing.images?.[0]
                      ? <img src={listing.images[0]} alt="" className="h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                      : <ImageOff className="h-4 w-4 text-neutral-400" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">{listing.title || j.url}</div>
                    <div className="text-xs text-neutral-500 flex items-center gap-2">
                      {listing.price != null && <span className="font-semibold tabular-nums text-neutral-700">${Number(listing.price).toFixed(2)}</span>}
                      {j.publish_status === "published" && <Badge className="bg-teal-100 text-teal-700 border-none text-[10px]">live</Badge>}
                      {j.publish_status && j.publish_status.startsWith("skipped") && <Badge variant="secondary" className="text-[10px]">skipped</Badge>}
                    </div>
                  </div>
                  <Badge className={`${meta.cls} border-none rounded-full text-xs flex items-center gap-1`}>
                    <StatusIcon className={`h-3 w-3 ${j.status === "running" ? "animate-spin" : ""}`} /> {meta.label}
                  </Badge>
                </div>
              );
            })}
          </div>

          <div className="flex gap-2 items-center">
            <Button variant="outline" onClick={reset} data-testid="scale-import-reset">Start another batch</Button>
            {published > 0 && (
              <a href="/profile?tab=listings" className="text-sm text-emerald-700 hover:underline inline-flex items-center gap-1">
                View your {published} live listing{published === 1 ? "" : "s"} <ArrowRight className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default CategoryScrapeAtScale;
