import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Bookmark, Plus, Play, Trash2, Loader2, Sparkles, Clock, Lightbulb, BarChart3, X } from "lucide-react";

const PROVIDERS = [
  { id: "amazon_search", label: "Amazon — search" },
  { id: "amazon_bestsellers", label: "Amazon — bestsellers" },
  { id: "mercari-global_search", label: "BlueOcean — search" },
];

const SavedSeeds = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    provider: "amazon_search",
    query: "",
    pages: 20,
    category_id: "",
    high_fidelity: false,
    enabled: true,
  });
  const [busy, setBusy] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [suggesting, setSuggesting] = useState(false);
  const [analytics, setAnalytics] = useState({}); // seed_id -> data

  const suggest = async () => {
    setSuggesting(true);
    try {
      const { data } = await api.get("/scraper/suggest-keywords");
      setSuggestions(data);
      if (!data.groups?.length) toast({ title: "No suggestions yet — publish a few listings first" });
    } catch (e) {
      toast({ title: "Couldn't fetch suggestions", variant: "destructive" });
    } finally { setSuggesting(false); }
  };

  const openAnalytics = async (row) => {
    if (analytics[row.id]) {
      setAnalytics((a) => { const n = { ...a }; delete n[row.id]; return n; });
      return;
    }
    setBusy(row.id + ":analytics");
    try {
      const { data } = await api.get(`/scraper/saved-seeds/${row.id}/analytics`);
      setAnalytics((a) => ({ ...a, [row.id]: data }));
    } catch (e) {
      toast({ title: "Failed to load analytics", variant: "destructive" });
    } finally { setBusy(null); }
  };

  const load = async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        api.get("/scraper/saved-seeds"),
        api.get("/categories"),
      ]);
      setRows(s.data.items || []);
      setCategories(c.data || []);
    } catch (e) {
      // ignore
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.query.trim() || !form.category_id) {
      toast({ title: "Fill keyword + category", variant: "destructive" });
      return;
    }
    setBusy("create");
    try {
      await api.post("/scraper/saved-seeds", form);
      toast({ title: "Saved seed added", description: "Runs every morning at 09:00 UTC." });
      setShowForm(false);
      setForm({ ...form, query: "" });
      await load();
    } catch (e) {
      toast({ title: "Save failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setBusy(null); }
  };

  const toggle = async (row) => {
    setBusy(row.id + ":toggle");
    try {
      await api.patch(`/scraper/saved-seeds/${row.id}`, { enabled: !row.enabled });
      await load();
    } catch (e) {
      toast({ title: "Toggle failed", variant: "destructive" });
    } finally { setBusy(null); }
  };

  const runNow = async (row) => {
    setBusy(row.id + ":run");
    try {
      const { data } = await api.post(`/scraper/saved-seeds/${row.id}/run`);
      toast({
        title: `Running ${row.query}`,
        description: `${data.pages_queued} pages queued — we'll email you when it's done.`,
      });
      await load();
    } catch (e) {
      toast({
        title: "Couldn't run seed",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally { setBusy(null); }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete saved seed "${row.query}"?`)) return;
    setBusy(row.id + ":del");
    try {
      await api.delete(`/scraper/saved-seeds/${row.id}`);
      await load();
    } catch (e) {
      toast({ title: "Delete failed", variant: "destructive" });
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6" data-testid="saved-seeds-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-sky-500 to-indigo-600 text-white grid place-items-center shrink-0">
            <Bookmark className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold">Saved seeds — hands-free catalog growth</h3>
            <p className="text-sm text-neutral-600 mt-1">
              Save a provider + keyword combo and we&apos;ll re-run it automatically <b>every morning at 09:00 UTC</b>. New products are auto-published live, deduped against ones you already imported, and you get an email when each run finishes.
            </p>
          </div>
        </div>
        <Button
          onClick={() => setShowForm(!showForm)}
          className="bg-[#DC2626] hover:bg-[#e01d1b]"
          data-testid="saved-seeds-add"
        >
          <Plus className="h-4 w-4 mr-1.5" /> {showForm ? "Cancel" : "Add seed"}
        </Button>
      </div>

      {showForm && (
        <div className="mt-4 p-4 rounded-xl bg-neutral-50 border border-neutral-200 space-y-3" data-testid="saved-seeds-form">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="text-xs text-neutral-600">Fill in the fields below, or let AI suggest high-signal keywords based on your top-selling categories.</div>
            <Button
              variant="outline" size="sm"
              onClick={suggest}
              disabled={suggesting}
              data-testid="suggest-keywords-btn"
            >
              {suggesting
                ? <><Loader2 className="h-3 w-3 mr-1.5 animate-spin" /> Thinking…</>
                : <><Lightbulb className="h-3 w-3 mr-1.5 text-amber-500" /> Suggest keywords</>}
            </Button>
          </div>
          {suggestions?.groups?.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 space-y-2" data-testid="suggestion-groups">
              <div className="text-xs font-semibold text-amber-800 flex items-center justify-between">
                <span>Suggestions {suggestions.llm_ok ? <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full ml-1">AI</span> : <span className="text-[10px] bg-neutral-100 text-neutral-600 px-1.5 py-0.5 rounded-full ml-1">Preset</span>}</span>
                <button className="text-neutral-500 hover:text-neutral-900" onClick={() => setSuggestions(null)}><X className="h-3 w-3" /></button>
              </div>
              {suggestions.groups.map((g) => (
                <div key={g.category_id}>
                  <div className="text-[11px] text-neutral-500 mb-1">{g.category_name}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {g.keywords.map((k) => (
                      <button
                        key={k}
                        onClick={() => setForm({ ...form, query: k, category_id: g.category_id })}
                        className="px-2.5 py-1 rounded-full bg-white border border-amber-300 text-xs font-medium hover:bg-amber-100 transition"
                        data-testid={`suggest-kw-${k.replace(/\s+/g, '-')}`}
                      >
                        {k}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label className="text-sm">Source</Label>
              <Select value={form.provider} onValueChange={(v) => setForm({ ...form, provider: v })}>
                <SelectTrigger className="mt-1 h-10" data-testid="saved-seed-provider"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">Pages per run (1-50)</Label>
              <Input
                type="number" min={1} max={50}
                value={form.pages}
                onChange={(e) => setForm({ ...form, pages: Math.max(1, Math.min(50, Number(e.target.value) || 1)) })}
                className="mt-1 h-10 tabular-nums"
                data-testid="saved-seed-pages"
              />
            </div>
          </div>
          <div>
            <Label className="text-sm">Keyword</Label>
            <Input
              value={form.query}
              onChange={(e) => setForm({ ...form, query: e.target.value })}
              placeholder="wireless headphones"
              className="mt-1 h-10"
              data-testid="saved-seed-query"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label className="text-sm">Category</Label>
              <Select value={form.category_id} onValueChange={(v) => setForm({ ...form, category_id: v })}>
                <SelectTrigger className="mt-1 h-10" data-testid="saved-seed-category"><SelectValue placeholder="Pick one" /></SelectTrigger>
                <SelectContent>
                  {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-amber-300 cursor-pointer transition-colors">
              <Switch checked={form.high_fidelity} onCheckedChange={(v) => setForm({ ...form, high_fidelity: v })} data-testid="saved-seed-hifi" />
              <div>
                <div className="text-sm font-semibold flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-amber-500" /> Amazon Full Pull</div>
                <div className="text-xs text-neutral-500 mt-0.5">Better for JS-heavy sources like Amazon.</div>
              </div>
            </label>
          </div>
          <Button onClick={create} disabled={busy === "create"} className="bg-emerald-600 hover:bg-emerald-700" data-testid="saved-seed-save">
            {busy === "create" ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Saving…</> : "Save seed"}
          </Button>
        </div>
      )}

      <div className="mt-4 space-y-2">
        {rows.length === 0 && (
          <div className="text-sm text-neutral-500 py-8 text-center border border-dashed border-neutral-200 rounded-lg">
            {loading ? "Loading…" : "No saved seeds yet. Add one to start nightly auto-imports."}
          </div>
        )}
        {rows.map((r) => (
          <div key={r.id} className="flex items-center gap-3 p-3 rounded-lg border border-neutral-200 hover:border-neutral-300 transition-colors" data-testid={`saved-seed-row-${r.id.slice(0,8)}`}>
            <div className="h-8 w-8 rounded-full bg-gradient-to-br from-sky-100 to-indigo-100 text-indigo-700 grid place-items-center shrink-0">
              <Bookmark className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold flex items-center gap-2 flex-wrap">
                <span>{r.query}</span>
                <Badge variant="secondary" className="text-[10px]">{(r.provider || "").replace("_", " ")}</Badge>
                <Badge className="bg-neutral-100 text-neutral-700 border-none text-[10px]">{r.pages}p</Badge>
                {r.high_fidelity && <Badge className="bg-amber-100 text-amber-700 border-none text-[10px]">hi-fi</Badge>}
              </div>
              <div className="text-xs text-neutral-500 mt-0.5 flex items-center gap-2">
                <Clock className="h-3 w-3" />
                {r.last_run_at ? `Last ran ${new Date(r.last_run_at).toLocaleString()}` : "Never run yet"}
              </div>
            </div>
            <Switch checked={!!r.enabled} onCheckedChange={() => toggle(r)} disabled={busy === r.id + ":toggle"} data-testid={`saved-seed-toggle-${r.id.slice(0,8)}`} />
            <Button
              variant="ghost" size="sm"
              onClick={() => openAnalytics(r)}
              disabled={busy === r.id + ":analytics"}
              data-testid={`saved-seed-analytics-${r.id.slice(0,8)}`}
              title="View history"
            >
              {busy === r.id + ":analytics" ? <Loader2 className="h-3 w-3 animate-spin" /> : <BarChart3 className="h-3 w-3" />}
            </Button>
            <Button
              variant="outline" size="sm"
              onClick={() => runNow(r)}
              disabled={busy === r.id + ":run" || !r.enabled}
              data-testid={`saved-seed-run-${r.id.slice(0,8)}`}
            >
              {busy === r.id + ":run" ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Play className="h-3 w-3 mr-1" /> Run</>}
            </Button>
            <Button
              variant="ghost" size="sm"
              onClick={() => remove(r)}
              disabled={busy === r.id + ":del"}
              data-testid={`saved-seed-del-${r.id.slice(0,8)}`}
            >
              <Trash2 className="h-3 w-3 text-red-500" />
            </Button>
          </div>
        ))}
        {rows.map((r) => analytics[r.id] && (
          <div key={r.id + "-analytics"} className="ml-11 p-3 rounded-lg bg-neutral-50 border border-neutral-100 text-xs space-y-2" data-testid={`saved-seed-analytics-panel-${r.id.slice(0,8)}`}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="bg-white rounded p-2">
                <div className="text-neutral-500 text-[10px]">Total runs</div>
                <div className="font-bold tabular-nums">{analytics[r.id].totals.runs}</div>
              </div>
              <div className="bg-white rounded p-2">
                <div className="text-neutral-500 text-[10px]">Avg products / run</div>
                <div className="font-bold tabular-nums">{analytics[r.id].averages.products_per_run}</div>
              </div>
              <div className="bg-white rounded p-2">
                <div className="text-neutral-500 text-[10px]">Live conversion</div>
                <div className="font-bold tabular-nums text-emerald-700">{analytics[r.id].averages.live_conversion_pct}%</div>
              </div>
              <div className="bg-white rounded p-2">
                <div className="text-neutral-500 text-[10px]">Total credits</div>
                <div className="font-bold tabular-nums">{analytics[r.id].totals.credits_spent}</div>
              </div>
            </div>
            {analytics[r.id].runs.slice(0, 8).length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold mt-1 mb-1">Recent runs</div>
                <div className="space-y-1">
                  {analytics[r.id].runs.slice(0, 8).map((run) => (
                    <div key={run.super_batch_id} className="flex justify-between items-center bg-white rounded px-2 py-1">
                      <span className="text-neutral-500 tabular-nums">{run.created_at ? new Date(run.created_at).toLocaleDateString() : "—"}</span>
                      <span className="tabular-nums">{run.products_published}/{run.products_extracted} live</span>
                      <span className="text-neutral-500 tabular-nums">{run.credits_spent}c</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default SavedSeeds;
