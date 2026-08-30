import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Search as SearchIcon, TrendingUp, AlertTriangle, RefreshCcw, Sparkles } from "lucide-react";

const WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
];

export default function AdminSearchInsights() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/admin/search/analytics", { params: { hours, limit: 25 } });
      setData(res.data);
    } catch (err) {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="max-w-6xl mx-auto space-y-6" data-testid="admin-search-insights">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            Search insights
          </h1>
          <p className="text-sm text-neutral-500 mt-1">
            What shoppers are typing, and what they can&apos;t find yet.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-full border border-neutral-200 dark:border-neutral-800 overflow-hidden">
            {WINDOWS.map((w) => (
              <button
                key={w.label}
                type="button"
                onClick={() => setHours(w.hours)}
                className={`px-3 h-8 text-xs font-medium transition ${
                  hours === w.hours
                    ? "bg-[#DC2626] text-white"
                    : "bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
                }`}
                data-testid={`admin-search-window-${w.label}`}
              >
                {w.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={load}
            className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 dark:border-neutral-800 px-3 h-8 text-xs text-neutral-600 dark:text-neutral-300 hover:border-[#DC2626]/50"
            data-testid="admin-search-refresh"
          >
            <RefreshCcw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
          <button
            type="button"
            onClick={async () => {
              try {
                const r = await api.post("/admin/search/vocab-refresh");
                toast.success(`Vocabulary refreshed · ${r.data.vocab_size.toLocaleString()} words`);
              } catch {
                toast.error("Vocab refresh failed");
              }
            }}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#DC2626] text-white px-3 h-8 text-xs font-medium hover:bg-[#e01d1b]"
            data-testid="admin-search-vocab-refresh"
            title="Rebuild the fuzzy-correction vocabulary from the past week of high-signal searches"
          >
            <Sparkles className="h-3 w-3" /> Grow vocab
          </button>
        </div>
      </header>

      {/* Stat strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Stat label="Total searches" value={data?.total_searches ?? 0} />
        <Stat label="Unique queries" value={data?.unique_queries ?? 0} />
        <Stat
          label="Correction rate"
          value={`${Math.round((data?.correction_rate ?? 0) * 100)}%`}
          hint="Fraction of queries we auto-corrected"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top queries */}
        <section className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl overflow-hidden">
          <header className="px-4 py-3 border-b border-neutral-100 dark:border-neutral-800 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-emerald-600" />
            <div className="font-semibold text-neutral-900 dark:text-neutral-100 text-sm">
              Top queries
            </div>
          </header>
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-neutral-500">
              <tr className="text-left">
                <th className="px-4 py-2 font-medium">Query</th>
                <th className="px-4 py-2 font-medium text-right">Searches</th>
                <th className="px-4 py-2 font-medium text-right">Avg results</th>
              </tr>
            </thead>
            <tbody data-testid="admin-search-top-queries">
              {(data?.top_queries || []).map((r) => (
                <tr key={r.query} className="border-t border-neutral-100 dark:border-neutral-800">
                  <td className="px-4 py-2 text-neutral-800 dark:text-neutral-200 truncate">
                    {r.query}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{r.count}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-neutral-500">{r.avg_results}</td>
                </tr>
              ))}
              {!loading && !data?.top_queries?.length && (
                <tr>
                  <td className="px-4 py-6 text-center text-neutral-500" colSpan={3}>
                    No searches yet in this window.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </section>

        {/* Zero-result queries */}
        <section className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl overflow-hidden">
          <header className="px-4 py-3 border-b border-neutral-100 dark:border-neutral-800 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <div className="font-semibold text-neutral-900 dark:text-neutral-100 text-sm">
              Zero-result queries
            </div>
            <span className="text-[10px] text-neutral-500 ml-1">
              Gaps to stock or vocabulary to grow
            </span>
          </header>
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-neutral-500">
              <tr className="text-left">
                <th className="px-4 py-2 font-medium">Query</th>
                <th className="px-4 py-2 font-medium text-right">Times</th>
                <th className="px-4 py-2 font-medium text-right">Last seen</th>
              </tr>
            </thead>
            <tbody data-testid="admin-search-zero-queries">
              {(data?.zero_result || []).map((r) => (
                <tr key={r.query} className="border-t border-neutral-100 dark:border-neutral-800">
                  <td className="px-4 py-2 text-neutral-800 dark:text-neutral-200 truncate">
                    <div className="flex items-center gap-1.5">
                      <SearchIcon className="h-3 w-3 text-neutral-400 shrink-0" />
                      {r.query}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold">{r.count}</td>
                  <td className="px-4 py-2 text-right text-xs text-neutral-500">
                    {r.last_seen ? new Date(r.last_seen).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                </tr>
              ))}
              {!loading && !data?.zero_result?.length && (
                <tr>
                  <td className="px-4 py-6 text-center text-neutral-500" colSpan={3}>
                    🎉 No zero-result searches — every query found something.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }) {
  return (
    <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl px-4 py-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="text-2xl font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      {hint ? <div className="text-[10px] text-neutral-400 mt-1">{hint}</div> : null}
    </div>
  );
}
