import React, { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Sparkles, Link as LinkIcon, Loader2, CheckCircle2, XCircle, Clock, ArrowRight, ImageOff } from "lucide-react";
import { Switch } from "@/components/ui/switch";

const STATUS_META = {
  queued:  { label: "Queued",   cls: "bg-neutral-100 text-neutral-700",   Icon: Clock },
  running: { label: "Running",  cls: "bg-sky-100 text-sky-700",           Icon: Loader2 },
  done:    { label: "Done",     cls: "bg-emerald-100 text-emerald-700",   Icon: CheckCircle2 },
  failed:  { label: "Failed",   cls: "bg-red-100 text-red-700",           Icon: XCircle },
};

const ImportFromUrl = ({ onImportReady }) => {
  const { toast } = useToast();
  const [url, setUrl] = useState("");
  const [highFidelity, setHighFidelity] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef(null);

  const loadJobs = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/scraper/jobs", { params: { limit: 20 } });
      setJobs(data.items || []);
    } catch (e) {
      // silent
    } finally { setLoading(false); }
  };

  useEffect(() => {
    loadJobs();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const anyPending = useMemo(
    () => jobs.some((j) => j.status === "queued" || j.status === "running"),
    [jobs],
  );

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (anyPending) pollRef.current = setInterval(loadJobs, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [anyPending]);

  const submit = async (e) => {
    e.preventDefault();
    if (!url.match(/^https?:\/\//i)) {
      toast({ title: "Enter a full https:// URL", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/scraper/jobs", { url, high_fidelity: highFidelity });
      toast({ title: "Import queued", description: "We'll extract the product data in the background." });
      setUrl("");
      await loadJobs();
    } catch (err) {
      toast({
        title: "Couldn't queue import",
        description: err?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setSubmitting(false); }
  };

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6" data-testid="import-from-url">
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white grid place-items-center shrink-0">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold">Import a product from any URL</h3>
          <p className="text-sm text-neutral-600 mt-1">
            Paste an Amazon, eBay, Shopify or Walmart URL and we&apos;ll pull the title, price and photos automatically. Images are rehosted to our CDN so listings never break when the supplier removes them.
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="mt-5 space-y-3">
        <div className="flex flex-wrap gap-2">
          <div className="flex-1 min-w-[220px] relative">
            <LinkIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.amazon.com/dp/…"
              className="pl-9 h-11"
              data-testid="import-url-input"
            />
          </div>
          <Button
            type="submit"
            disabled={submitting}
            className="h-11 bg-[#DC2626] hover:bg-[#e01d1b]"
            data-testid="import-url-submit"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : (<>Import <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
          </Button>
        </div>
        <label className="flex items-center gap-2 text-xs text-neutral-600 cursor-pointer select-none pl-1">
          <Switch
            checked={highFidelity}
            onCheckedChange={setHighFidelity}
            data-testid="import-hifi-toggle"
          />
          <span><span className="font-semibold text-neutral-800">Amazon Full Pull</span> — force browser rendering + anti-bot proxy for JS-heavy sites (uses more Zyte credits)</span>
        </label>
      </form>

      <div className="mt-6">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-semibold text-neutral-700">Recent imports</div>
          <button onClick={loadJobs} className="text-xs text-neutral-500 hover:text-neutral-800">
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <div className="space-y-2">
          {jobs.length === 0 && (
            <div className="text-xs text-neutral-500 py-6 text-center border border-dashed border-neutral-200 rounded-lg">
              No imports yet — paste a URL above to try it.
            </div>
          )}
          {jobs.map((j) => {
            const meta = STATUS_META[j.status] || STATUS_META.queued;
            const listing = j.result?.listing || {};
            const StatusIcon = meta.Icon;
            return (
              <div key={j.id} className="flex items-center gap-3 p-3 rounded-lg border border-neutral-100 hover:border-neutral-200 transition-colors" data-testid={`import-job-row-${j.id.slice(0,8)}`}>
                <div className="h-12 w-12 rounded-md bg-neutral-100 overflow-hidden shrink-0 grid place-items-center">
                  {listing.images?.[0]
                    ? <img src={listing.images[0]} alt="" className="h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                    : <ImageOff className="h-5 w-5 text-neutral-400" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">
                    {listing.title || j.url}
                  </div>
                  <div className="text-xs text-neutral-500 flex items-center gap-2 mt-0.5">
                    <a href={j.url} target="_blank" rel="noreferrer" className="hover:underline truncate max-w-[220px] inline-block">
                      {new URL(j.url).hostname}
                    </a>
                    {listing.price !== undefined && listing.price !== null && (
                      <span className="tabular-nums font-semibold text-neutral-700">${Number(listing.price).toFixed(2)}</span>
                    )}
                  </div>
                </div>
                <Badge className={`${meta.cls} border-none rounded-full text-xs flex items-center gap-1`}>
                  <StatusIcon className={`h-3 w-3 ${j.status === "running" ? "animate-spin" : ""}`} />
                  {meta.label}
                </Badge>
                {j.status === "done" && onImportReady && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onImportReady(listing, j)}
                    data-testid={`import-use-${j.id.slice(0,8)}`}
                  >
                    Use
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ImportFromUrl;
