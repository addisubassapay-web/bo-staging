import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RefreshCw, Zap, Database, Cloud, Server, CheckCircle2, XCircle, Clock, Loader2, AlertCircle } from "lucide-react";

const STATUS_META = {
  queued:  { label: "Queued",   cls: "bg-neutral-100 text-neutral-700",   Icon: Clock },
  running: { label: "Running",  cls: "bg-sky-100 text-sky-700",           Icon: Loader2 },
  done:    { label: "Done",     cls: "bg-emerald-100 text-emerald-700",   Icon: CheckCircle2 },
  failed:  { label: "Failed",   cls: "bg-red-100 text-red-700",           Icon: XCircle },
};

const HealthPill = ({ label, ok, sub, Icon }) => (
  <div className="rounded-xl border border-neutral-200 bg-white p-4 flex items-center gap-3">
    <div className={`h-10 w-10 rounded-full grid place-items-center ${ok ? "bg-emerald-100 text-emerald-700" : "bg-neutral-100 text-neutral-500"}`}>
      <Icon className="h-5 w-5" />
    </div>
    <div className="min-w-0 flex-1">
      <div className="text-sm font-semibold flex items-center gap-2">
        {label}
        {ok
          ? <Badge className="bg-emerald-100 text-emerald-700 border-none text-[10px]">live</Badge>
          : <Badge variant="secondary" className="text-[10px]">off</Badge>}
      </div>
      {sub && <div className="text-xs text-neutral-500 mt-0.5 truncate">{sub}</div>}
    </div>
  </div>
);

const AdminScraper = () => {
  const [status, setStatus] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, j] = await Promise.all([
        api.get("/scraper/status"),
        api.get("/scraper/admin/jobs", { params: filter ? { status: filter, limit: 200 } : { limit: 200 } }),
      ]);
      setStatus(s.data);
      setJobs(j.data.items || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const i = setInterval(load, 5000); return () => clearInterval(i); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const failedCount = useMemo(() => jobs.filter((j) => j.status === "failed").length, [jobs]);

  return (
    <div className="space-y-6" data-testid="admin-scraper-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Zap className="h-6 w-6" /> Zyte scraper pipeline
          </h2>
          <p className="text-sm text-neutral-500 mt-1">
            Every import from a supplier URL flows through Zyte extraction → arq queue → Cloudflare R2 rehost.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="admin-scraper-refresh">
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {status && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <HealthPill label="Zyte API" ok={status.zyte?.enabled} sub={status.zyte?.enabled ? "Key configured" : "Set ZYTE_API_KEY"} Icon={Cloud} />
          <HealthPill label="arq queue" ok={status.queue?.redis_ok} sub={status.queue?.redis_url} Icon={Server} />
          <HealthPill label="Cloudflare R2" ok={status.storage?.enabled} sub={status.storage?.enabled ? status.storage?.bucket : "Add R2_* env vars"} Icon={Database} />
        </div>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-neutral-600">Status</span>
          <Select value={filter || "__all__"} onValueChange={(v) => setFilter(v === "__all__" ? "" : v)}>
            <SelectTrigger className="w-40" data-testid="admin-scraper-filter">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All</SelectItem>
              <SelectItem value="queued">Queued</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="done">Done</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {failedCount > 0 && (
          <Badge variant="destructive" className="rounded-full px-3">
            <AlertCircle className="h-3 w-3 mr-1" /> {failedCount} failed
          </Badge>
        )}
        <div className="text-xs text-neutral-500 ml-auto">Auto-refreshes every 5s</div>
      </div>

      <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-neutral-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-3">Created</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Owner</th>
                <th className="text-left px-4 py-3">URL</th>
                <th className="text-left px-4 py-3">Extracted</th>
                <th className="text-left px-4 py-3">Mode</th>
                <th className="text-left px-4 py-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-neutral-500">
                  {loading ? "Loading…" : "No scraper jobs yet."}
                </td></tr>
              )}
              {jobs.map((j) => {
                const meta = STATUS_META[j.status] || STATUS_META.queued;
                const StatusIcon = meta.Icon;
                const listing = j.result?.listing || {};
                const host = (() => { try { return new URL(j.url).hostname; } catch { return j.url; } })();
                const created = j.created_at ? new Date(j.created_at).toLocaleString() : "—";
                const err = j.error ? (j.error.message || JSON.stringify(j.error.detail || j.error).slice(0, 120)) : "";
                return (
                  <tr key={j.id} className={`border-t border-neutral-100 ${j.status === "failed" ? "bg-red-50/50" : ""}`} data-testid={`admin-scraper-row-${j.id.slice(0,8)}`}>
                    <td className="px-4 py-3 whitespace-nowrap text-neutral-600 tabular-nums text-xs">{created}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${meta.cls}`}>
                        <StatusIcon className={`h-3 w-3 ${j.status === "running" ? "animate-spin" : ""}`} /> {meta.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-600 truncate max-w-[160px]">{j.owner_email || j.owner_id?.slice(0,8)}</td>
                    <td className="px-4 py-3">
                      <a href={j.url} target="_blank" rel="noreferrer" className="text-xs text-sky-600 hover:underline">{host}</a>
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate text-xs" title={listing.title}>
                      {listing.title || "—"}
                      {listing.price != null && <span className="ml-2 text-neutral-500">${Number(listing.price).toFixed(2)}</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-500">{listing.extract_from || "—"}</td>
                    <td className="px-4 py-3 text-xs text-red-600 max-w-xs truncate" title={err}>{err}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AdminScraper;
