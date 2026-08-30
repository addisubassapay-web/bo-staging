import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import {
  Terminal,
  RefreshCw,
  StopCircle,
  RotateCw,
  Copy as CopyIcon,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

const STATUS_TONE = {
  RUNNING: "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
  SUCCEEDED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-200",
  "TIMED-OUT": "bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-200",
  ABORTED: "bg-neutral-200 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
  READY: "bg-blue-100 text-blue-800 dark:bg-blue-950/40 dark:text-blue-200",
};

const shortId = (id) => (id ? id.slice(0, 6) + "…" + id.slice(-4) : "");

const ApifyRunConsole = () => {
  const { toast } = useToast();
  const [runs, setRuns] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [run, setRun] = useState(null);
  const [log, setLog] = useState("");
  const [items, setItems] = useState([]);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadRuns = useCallback(async () => {
    setLoadingRuns(true);
    try {
      const { data } = await api.get("/admin/apify/runs", { params: { limit: 20 } });
      const list = Array.isArray(data) ? data : data?.items || [];
      setRuns(list);
      if (list.length && !selectedRunId) setSelectedRunId(list[0].id);
    } catch (err) {
      toast({
        title: "Failed to load runs",
        description: err.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setLoadingRuns(false);
    }
  }, [selectedRunId, toast]);

  const loadRunDetails = useCallback(
    async (runId) => {
      if (!runId) return;
      setBusy(true);
      try {
        const [runRes, logRes] = await Promise.all([
          api.get(`/admin/apify/runs/${runId}`),
          api.get(`/admin/apify/runs/${runId}/log`, { params: { tail_bytes: 8000 } }),
        ]);
        setRun(runRes.data);
        setLog(logRes.data?.log || "");
        const dsId = runRes.data?.defaultDatasetId;
        if (dsId) {
          try {
            const { data: dsItems } = await api.get(
              `/admin/apify/datasets/${dsId}/items`,
              { params: { limit: 5 } }
            );
            setItems(Array.isArray(dsItems) ? dsItems : dsItems?.items || []);
          } catch {
            setItems([]);
          }
        } else {
          setItems([]);
        }
      } catch (err) {
        toast({
          title: "Failed to load run",
          description: err.response?.data?.detail || "Try again",
          variant: "destructive",
        });
      } finally {
        setBusy(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (selectedRunId) loadRunDetails(selectedRunId);
  }, [selectedRunId, loadRunDetails]);

  // Auto-refresh every 5s while the selected run is RUNNING
  useEffect(() => {
    if (run?.status !== "RUNNING") return;
    const iv = setInterval(() => loadRunDetails(selectedRunId), 5000);
    return () => clearInterval(iv);
  }, [run?.status, selectedRunId, loadRunDetails]);

  const doAction = async (action) => {
    if (!selectedRunId) return;
    if (action === "abort" && !window.confirm("Abort this run? It will stop immediately.")) return;
    setBusy(true);
    try {
      await api.post(`/admin/apify/runs/${selectedRunId}/${action}`);
      toast({
        title: action === "abort" ? "Run aborted" : "Run resurrected",
        description: shortId(selectedRunId),
      });
      await loadRunDetails(selectedRunId);
      await loadRuns();
    } catch (err) {
      toast({
        title: `${action} failed`,
        description: err.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  const copyId = (id) => {
    navigator.clipboard?.writeText(id);
    toast({ title: "Copied", description: id });
  };

  const status = run?.status;
  const canAbort = status === "RUNNING" || status === "READY";
  const canResurrect =
    status === "SUCCEEDED" ||
    status === "FAILED" ||
    status === "TIMED-OUT" ||
    status === "ABORTED";

  return (
    <div
      className="mt-6 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-5"
      data-testid="apify-run-console"
    >
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-[#DC2626]" />
          <h3 className="font-semibold">Run Console</h3>
          <span className="text-xs text-neutral-500">
            Inspect · abort · resurrect any Apify actor run
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Or paste a run ID…"
            value={selectedRunId}
            onChange={(e) => setSelectedRunId(e.target.value.trim())}
            className="w-56 font-mono text-xs"
            data-testid="apify-run-id-input"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={loadRuns}
            disabled={loadingRuns}
            data-testid="apify-refresh-runs-btn"
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${loadingRuns ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {runs.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <div className="flex gap-2 pb-2 min-w-max">
            {runs.slice(0, 10).map((r) => {
              const active = r.id === selectedRunId;
              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setSelectedRunId(r.id)}
                  className={`text-left px-3 py-2 rounded-lg border transition ${
                    active
                      ? "border-[#DC2626] bg-red-50 dark:bg-red-950/20"
                      : "border-neutral-200 dark:border-neutral-800 hover:border-neutral-400"
                  }`}
                  data-testid={`apify-run-chip-${r.id}`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${
                        STATUS_TONE[r.status] || "bg-neutral-100 text-neutral-700"
                      }`}
                    >
                      {r.status}
                    </span>
                    <span className="font-mono text-[11px] text-neutral-600 dark:text-neutral-300">
                      {shortId(r.id)}
                    </span>
                  </div>
                  <div className="text-[10px] text-neutral-500 mt-0.5">
                    {r.startedAt ? new Date(r.startedAt).toLocaleString() : "—"}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {run ? (
        <div className="mt-4 space-y-4">
          <div className="grid sm:grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-xs text-neutral-500">Run ID</div>
              <div className="flex items-center gap-1 font-mono text-xs">
                <span data-testid="apify-run-id-display">{run.id}</span>
                <button
                  onClick={() => copyId(run.id)}
                  className="text-neutral-400 hover:text-neutral-800"
                  aria-label="Copy run id"
                >
                  <CopyIcon className="h-3 w-3" />
                </button>
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">Status</div>
              <Badge
                className={`${STATUS_TONE[status] || "bg-neutral-100 text-neutral-700"} border-0`}
                data-testid="apify-run-status"
              >
                {status || "—"}
              </Badge>
            </div>
            <div>
              <div className="text-xs text-neutral-500">Started</div>
              <div>{run.startedAt ? new Date(run.startedAt).toLocaleString() : "—"}</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">Finished</div>
              <div>{run.finishedAt ? new Date(run.finishedAt).toLocaleString() : "—"}</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">Dataset</div>
              <div className="font-mono text-xs">{run.defaultDatasetId || "—"}</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">KV store</div>
              <div className="font-mono text-xs">{run.defaultKeyValueStoreId || "—"}</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => loadRunDetails(selectedRunId)}
              disabled={busy}
              data-testid="apify-run-reload-btn"
            >
              <RefreshCw className={`h-4 w-4 mr-1 ${busy ? "animate-spin" : ""}`} />
              Reload
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!canAbort || busy}
              onClick={() => doAction("abort")}
              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
              data-testid="apify-run-abort-btn"
            >
              <StopCircle className="h-4 w-4 mr-1" /> Abort
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!canResurrect || busy}
              onClick={() => doAction("resurrect")}
              className="text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50 dark:hover:bg-emerald-950/30"
              data-testid="apify-run-resurrect-btn"
            >
              <RotateCw className="h-4 w-4 mr-1" /> Resurrect
            </Button>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="ml-auto text-xs text-neutral-500 hover:text-neutral-800 inline-flex items-center gap-0.5"
              data-testid="apify-run-toggle-details"
            >
              {expanded ? (
                <>
                  Hide log & items <ChevronUp className="h-3 w-3" />
                </>
              ) : (
                <>
                  Show log & items <ChevronDown className="h-3 w-3" />
                </>
              )}
            </button>
          </div>

          {expanded && (
            <div className="space-y-3">
              <div>
                <div className="text-xs font-semibold text-neutral-600 dark:text-neutral-300 mb-1">
                  Log tail (last 8 KB)
                </div>
                <pre
                  className="bg-neutral-950 text-neutral-100 rounded-md p-3 text-[11px] leading-snug overflow-x-auto max-h-64 font-mono whitespace-pre-wrap"
                  data-testid="apify-run-log"
                >
                  {log || "(no log yet)"}
                </pre>
              </div>
              {items.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-neutral-600 dark:text-neutral-300 mb-1">
                    Dataset preview — first {items.length} item{items.length > 1 ? "s" : ""}
                  </div>
                  <pre
                    className="bg-neutral-50 dark:bg-neutral-800/60 rounded-md p-3 text-[11px] overflow-x-auto max-h-64 font-mono"
                    data-testid="apify-run-items"
                  >
                    {JSON.stringify(items, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 text-sm text-neutral-500 py-6 text-center">
          {loadingRuns ? "Loading runs…" : "Pick a run above or paste a run ID."}
        </div>
      )}
    </div>
  );
};

export default ApifyRunConsole;
