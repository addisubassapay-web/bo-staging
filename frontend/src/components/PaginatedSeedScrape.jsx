import React, { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { Rocket, Loader2, ArrowRight, Sparkles, ExternalLink } from "lucide-react";

const PROVIDERS = [
  { id: "amazon_search",       label: "Amazon — search results", example: "wireless headphones" },
  { id: "amazon_bestsellers",  label: "Amazon — bestsellers category", example: "electronics" },
  { id: "mercuri-global_search",      label: "Mercuri-global — search results", example: "vintage denim" },
];

const PaginatedSeedScrape = () => {
  const { toast } = useToast();
  const [provider, setProvider] = useState("amazon_search");
  const [query, setQuery] = useState("");
  const [pages, setPages] = useState(10);
  const [categoryId, setCategoryId] = useState("");
  const [autoPublish, setAutoPublish] = useState(true);
  const [highFidelity, setHighFidelity] = useState(false);
  const [categories, setCategories] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [superId, setSuperId] = useState(null);
  const [state, setState] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!superId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const { data } = await api.get(`/scraper/super-batches/${superId}`);
        if (cancelled) return;
        setState(data);
        const totalPages = data.pages_total || 1;
        if ((data.pages_done + data.pages_failed) >= totalPages && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch { /* ignore */ }
    };
    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => { cancelled = true; if (pollRef.current) clearInterval(pollRef.current); };
  }, [superId]);

  const example = useMemo(() => PROVIDERS.find((p) => p.id === provider)?.example || "", [provider]);

  const submit = async () => {
    if (!query.trim()) {
      toast({ title: "Enter a search query", variant: "destructive" });
      return;
    }
    if (autoPublish && !categoryId) {
      toast({ title: "Pick a category first", description: "Auto-publish needs a category.", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    setState(null);
    try {
      const { data } = await api.post("/scraper/jobs/paginated", {
        provider, query, pages,
        category_id: categoryId || null,
        auto_publish: autoPublish,
        high_fidelity: highFidelity,
      });
      setSuperId(data.super_batch_id);
      toast({
        title: `Walking ${data.pages_queued} pages of ${provider.split("_")[0]}`,
        description: `${data.pages_queued} Zyte credits will be used.`,
      });
    } catch (e) {
      toast({
        title: "Seed scrape failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setSubmitting(false); }
  };

  const reset = () => { setSuperId(null); setState(null); setQuery(""); };

  return (
    <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50/30 to-white p-4 sm:p-6" data-testid="paginated-seed-panel">
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-emerald-500 to-lime-500 text-white grid place-items-center shrink-0">
          <Rocket className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold">Paginated seed — Amazon &amp; Mercuri-global at scale</h3>
          <p className="text-sm text-neutral-600 mt-1">
            Enter a keyword, pick how many pages to crawl, and we&apos;ll walk them all. Each page is <span className="font-semibold text-emerald-700">1 Zyte credit</span> and typically yields 30-60 live products — 10 pages ≈ 300-600 listings.
          </p>
        </div>
      </div>

      {!superId && (
        <div className="mt-5 grid grid-cols-1 gap-4">
          {/* One-click "Seed 1,000" preset — fills the form + fires submit */}
          <button
            type="button"
            onClick={() => {
              setPages(20);
              setAutoPublish(true);
              setHighFidelity(provider === "amazon_search" || provider === "amazon_bestsellers");
            }}
            className="w-full text-left rounded-xl border border-dashed border-emerald-300 bg-emerald-50/40 hover:bg-emerald-50 p-3.5 transition-colors group"
            data-testid="seed-preset-1000"
          >
            <div className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-full bg-emerald-600 text-white grid place-items-center shrink-0 group-hover:scale-105 transition-transform">
                <Rocket className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-emerald-900">Preset: Seed ~1,000 products in one click</div>
                <div className="text-xs text-emerald-700/80 mt-0.5">Auto-fills 20 pages + Auto-Publish + Amazon Full Pull (for Amazon). Cost: ~20 Zyte credits. Just add a keyword and a category, then hit Crawl. We&apos;ll email you when it&apos;s done.</div>
              </div>
              <div className="text-xs font-bold text-emerald-700 whitespace-nowrap">Apply →</div>
            </div>
          </button>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Source</Label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger className="mt-1 h-10" data-testid="seed-provider"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">Pages to walk (1-50)</Label>
              <Input
                type="number" min={1} max={50}
                value={pages}
                onChange={(e) => setPages(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
                className="mt-1 h-10 tabular-nums"
                data-testid="seed-pages"
              />
            </div>
          </div>

          <div>
            <Label className="text-sm">Keyword / category slug</Label>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={example}
              className="mt-1 h-10"
              data-testid="seed-query"
            />
            <div className="text-xs text-neutral-500 mt-1">Try: <span className="font-mono">{example}</span></div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Target category {autoPublish && <span className="text-[#FF211F]">*</span>}</Label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger className="mt-1 h-10" data-testid="seed-category-select"><SelectValue placeholder="Choose a category" /></SelectTrigger>
                <SelectContent>
                  {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <label className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-emerald-300 cursor-pointer transition-colors">
                <Switch checked={autoPublish} onCheckedChange={setAutoPublish} data-testid="seed-autopublish" />
                <div>
                  <div className="text-sm font-semibold flex items-center gap-1.5"><Rocket className="h-3.5 w-3.5 text-emerald-600" /> Auto-publish live</div>
                  <div className="text-xs text-neutral-500 mt-0.5">Every product becomes a live listing immediately.</div>
                </div>
              </label>
              <label className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-amber-300 cursor-pointer transition-colors">
                <Switch checked={highFidelity} onCheckedChange={setHighFidelity} data-testid="seed-hifi" />
                <div>
                  <div className="text-sm font-semibold flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-amber-500" /> Amazon Full Pull</div>
                  <div className="text-xs text-neutral-500 mt-0.5">Force browser rendering. Consumes more Zyte credits per page.</div>
                </div>
              </label>
            </div>
          </div>

          <Button
            onClick={submit}
            disabled={submitting}
            className="bg-[#FF211F] hover:bg-[#e01d1b] h-11 w-full sm:w-auto"
            data-testid="seed-submit"
          >
            {submitting
              ? (<><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Queueing…</>)
              : (<>Crawl {pages} page{pages === 1 ? "" : "s"} <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
          </Button>
          <div className="text-xs text-neutral-500">Estimated cost: <span className="font-semibold text-neutral-700">{pages} Zyte credit{pages === 1 ? "" : "s"}</span>.</div>
        </div>
      )}

      {superId && (
        <div className="mt-5 space-y-4">
          <div className="rounded-xl border border-neutral-200 bg-white p-4">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <div className="text-sm font-semibold">Pages walked</div>
              <div className="flex items-center gap-1.5 text-xs">
                <Badge className="bg-emerald-100 text-emerald-700 border-none">{state?.pages_done || 0} done</Badge>
                {state?.pages_failed > 0 && <Badge variant="destructive">{state.pages_failed} failed</Badge>}
                <Badge className="bg-neutral-100 text-neutral-700 border-none">{(state?.pages_total || 0) - (state?.pages_done || 0) - (state?.pages_failed || 0)} pending</Badge>
              </div>
            </div>
            <Progress value={state ? Math.round(((state.pages_done + state.pages_failed) / (state.pages_total || 1)) * 100) : 0} className="h-2" />
            <div className="text-xs text-neutral-500 mt-2 flex items-center justify-between">
              <span>{state?.pages_total || 0} page{state?.pages_total === 1 ? "" : "s"}</span>
              <span className="tabular-nums">
                <span className="font-semibold text-emerald-700">{state?.products_published || 0}</span> live •&nbsp;
                <span className="font-semibold">{state?.products_total || 0}</span> extracted
              </span>
            </div>
          </div>

          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {(state?.children || []).map((c) => {
              const pct = c.status === "done" ? 100 : c.status === "running" ? 60 : c.status === "failed" ? 100 : 0;
              return (
                <div key={c.id} className="flex items-center gap-3 p-3 rounded-lg border border-neutral-100" data-testid={`seed-page-${c.page}`}>
                  <div className="w-6 h-6 rounded-full bg-neutral-100 grid place-items-center text-[10px] font-bold text-neutral-600 shrink-0">{c.page}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-neutral-500 truncate">{c.source_url}</div>
                    <Progress value={pct} className={`h-1 mt-1 ${c.status === "failed" ? "[&>div]:bg-red-500" : ""}`} />
                  </div>
                  <Badge variant="secondary" className="text-[10px] uppercase">{c.status}</Badge>
                  <span className="text-xs tabular-nums text-neutral-600 w-10 text-right">{c.total || 0}</span>
                </div>
              );
            })}
          </div>

          <div className="flex gap-2 items-center flex-wrap">
            <Button variant="outline" onClick={reset} data-testid="seed-reset">Start another crawl</Button>
            {(state?.products_published || 0) > 0 && (
              <a href="/profile?tab=listings" className="text-sm text-emerald-700 hover:underline inline-flex items-center gap-1" data-testid="seed-view-listings">
                View your {state.products_published} live listings <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PaginatedSeedScrape;
