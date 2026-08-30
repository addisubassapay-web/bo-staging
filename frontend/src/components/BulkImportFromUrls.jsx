import React, { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { Layers, Loader2, ArrowRight, CheckCircle2, XCircle, Clock, Sparkles, ImageOff } from "lucide-react";

const MAX_URLS = 20;
const STATUS_META = {
  queued:  { label: "Queued",   cls: "bg-neutral-100 text-neutral-700",   Icon: Clock },
  running: { label: "Running",  cls: "bg-sky-100 text-sky-700",           Icon: Loader2 },
  done:    { label: "Done",     cls: "bg-emerald-100 text-emerald-700",   Icon: CheckCircle2 },
  failed:  { label: "Failed",   cls: "bg-red-100 text-red-700",           Icon: XCircle },
};

const BulkImportFromUrls = ({ onUseListing }) => {
  const { toast } = useToast();
  const [text, setText] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [highFidelity, setHighFidelity] = useState(false);
  const [categories, setCategories] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [batchId, setBatchId] = useState(null);
  const [batchState, setBatchState] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
  }, []);

  const urls = useMemo(
    () => text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean).slice(0, MAX_URLS),
    [text],
  );
  const overLimit = text.split(/\r?\n/).filter((s) => s.trim()).length > MAX_URLS;

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const { data } = await api.get(`/scraper/batches/${batchId}`);
        if (cancelled) return;
        setBatchState(data);
        const active = (data.counts?.queued || 0) + (data.counts?.running || 0);
        if (active === 0) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
      } catch (e) { /* ignore */ }
    };
    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => { cancelled = true; if (pollRef.current) clearInterval(pollRef.current); };
  }, [batchId]);

  const submit = async () => {
    if (urls.length === 0) {
      toast({ title: "Paste at least 1 URL", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    setBatchState(null);
    try {
      const { data } = await api.post("/scraper/jobs/bulk", {
        urls,
        category_id: categoryId || null,
        high_fidelity: highFidelity,
      });
      setBatchId(data.batch_id);
      toast({
        title: `Queued ${data.queued_count} of ${urls.length}`,
        description: data.rejected?.length ? `${data.rejected.length} rejected — see the list below.` : "Extraction running in the background.",
      });
    } catch (e) {
      toast({
        title: "Bulk import failed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setSubmitting(false); }
  };

  const reset = () => {
    setBatchId(null); setBatchState(null); setText("");
  };

  const doneCount = batchState?.counts?.done || 0;
  const totalCount = batchState?.total || urls.length || 1;
  const progressPct = totalCount ? Math.round(((doneCount + (batchState?.counts?.failed || 0)) / totalCount) * 100) : 0;
  const jobs = batchState?.jobs || [];

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6" data-testid="bulk-import-panel">
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white grid place-items-center shrink-0">
          <Layers className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold">Bulk import up to {MAX_URLS} URLs</h3>
          <p className="text-sm text-neutral-600 mt-1">
            Paste one URL per line and pick a category once for the whole batch. Zyte extracts them in parallel; you review and publish when they&apos;re done.
          </p>
        </div>
      </div>

      {!batchId && (
        <div className="mt-5 space-y-4">
          <div>
            <Label className="text-sm">URLs</Label>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="https://www.amazon.com/dp/…&#10;https://www.walmart.com/ip/…&#10;https://www.ebay.com/itm/…"
              rows={7}
              className="mt-1 font-mono text-xs"
              data-testid="bulk-import-urls"
            />
            <div className="flex justify-between text-xs mt-1">
              <span className="text-neutral-500">{urls.length} of {MAX_URLS} URLs</span>
              {overLimit && <span className="text-red-600">Only the first {MAX_URLS} will be used</span>}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Category (applied to all)</Label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger className="mt-1 h-10" data-testid="bulk-import-category">
                  <SelectValue placeholder="Choose a category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <label className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-neutral-300 cursor-pointer transition-colors w-full">
                <Switch
                  checked={highFidelity}
                  onCheckedChange={setHighFidelity}
                  data-testid="bulk-import-hifi"
                />
                <div>
                  <div className="text-sm font-semibold flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-amber-500" /> Amazon Full Pull
                  </div>
                  <div className="text-xs text-neutral-500 mt-0.5">Force browser rendering + anti-bot proxy for JS-heavy sites like Amazon. Costs more Zyte credits.</div>
                </div>
              </label>
            </div>
          </div>

          <Button
            onClick={submit}
            disabled={submitting || urls.length === 0}
            className="w-full sm:w-auto bg-[#DC2626] hover:bg-[#e01d1b] h-11"
            data-testid="bulk-import-submit"
          >
            {submitting ? (<><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Queueing…</>) : (<>Import {urls.length} URLs <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
          </Button>
        </div>
      )}

      {batchId && (
        <div className="mt-5 space-y-4">
          <div className="rounded-xl border border-neutral-200 bg-neutral-50/50 p-4">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <div className="text-sm font-semibold">Batch progress</div>
              <div className="flex items-center gap-1.5 text-xs">
                <Badge className="bg-emerald-100 text-emerald-700 border-none">{batchState?.counts?.done || 0} done</Badge>
                <Badge className="bg-sky-100 text-sky-700 border-none">{batchState?.counts?.running || 0} running</Badge>
                <Badge className="bg-neutral-200 text-neutral-700 border-none">{batchState?.counts?.queued || 0} queued</Badge>
                {(batchState?.counts?.failed || 0) > 0 && <Badge variant="destructive">{batchState.counts.failed} failed</Badge>}
              </div>
            </div>
            <Progress value={progressPct} className="h-2" />
            <div className="text-xs text-neutral-500 mt-2">{progressPct}% • {batchState?.total || 0} URLs</div>
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {jobs.map((j) => {
              const meta = STATUS_META[j.status] || STATUS_META.queued;
              const StatusIcon = meta.Icon;
              const listing = j.result?.listing || {};
              const host = (() => { try { return new URL(j.url).hostname; } catch { return j.url; } })();
              return (
                <div key={j.id} className="flex items-center gap-3 p-2.5 rounded-lg border border-neutral-100" data-testid={`bulk-job-${j.id.slice(0,8)}`}>
                  <div className="h-10 w-10 rounded bg-neutral-100 grid place-items-center overflow-hidden shrink-0">
                    {listing.images?.[0]
                      ? <img src={listing.images[0]} alt="" className="h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                      : <ImageOff className="h-4 w-4 text-neutral-400" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">{listing.title || host}</div>
                    <div className="text-xs text-neutral-500">
                      {host}
                      {listing.price != null && <span className="ml-2 font-semibold text-neutral-700 tabular-nums">${Number(listing.price).toFixed(2)}</span>}
                    </div>
                  </div>
                  <Badge className={`${meta.cls} border-none rounded-full text-xs flex items-center gap-1`}>
                    <StatusIcon className={`h-3 w-3 ${j.status === "running" ? "animate-spin" : ""}`} /> {meta.label}
                  </Badge>
                  {j.status === "done" && onUseListing && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onUseListing(listing, j)}
                      data-testid={`bulk-use-${j.id.slice(0,8)}`}
                    >
                      Use
                    </Button>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex gap-2">
            <Button variant="outline" onClick={reset} data-testid="bulk-import-reset">Start another batch</Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default BulkImportFromUrls;
