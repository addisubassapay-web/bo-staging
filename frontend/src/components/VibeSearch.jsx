import React, { useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Sparkles, Wand2, Loader2, X } from "lucide-react";

const VIBE_EXAMPLES = [
  "cozy minimalist home",
  "y2k retro glam",
  "streetwear athleisure",
  "vintage tech collectibles",
  "beach summer picnic",
  "office desk setup",
];

/**
 * VibeSearch — Emergent-LLM powered natural-language search.
 * POST /api/search/vibe -> {explanation, keywords, categories, brand_hints, items}
 */
const VibeSearch = () => {
  const [vibe, setVibe] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const runVibe = async (text) => {
    const v = (text ?? vibe).trim();
    if (v.length < 2) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const { data } = await api.post("/search/vibe", { vibe: v, limit: 24 });
      setResult(data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Vibe search failed. Try a simpler vibe.");
    } finally {
      setLoading(false);
    }
  };

  const clearAll = () => {
    setVibe("");
    setResult(null);
    setError("");
  };

  return (
    <div className="mb-8" data-testid="vibe-search">
      {/* Input pill */}
      <div className="rounded-3xl border border-[#FF7A18]/30 bg-gradient-to-br from-[#FF7A18]/5 via-white to-[#FF211F]/5 dark:from-[#3a1817]/40 dark:via-neutral-900 dark:to-[#3a1817]/40 p-4 sm:p-6 shadow-sm">
        <div className="flex items-start gap-3 sm:gap-4">
          <div className="h-11 w-11 shrink-0 rounded-2xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center shadow-md">
            <Wand2 className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18]">Search by vibe</span>
              <span className="text-[11px] px-2 h-5 rounded-full bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 font-semibold grid place-items-center">AI</span>
            </div>
            <h3 className="mt-1 text-xl sm:text-2xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
              Describe how you want to feel
            </h3>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              We&apos;ll translate your vibe into categories, brands, and keywords — then find matching finds.
            </p>

            <form
              onSubmit={(e) => { e.preventDefault(); runVibe(); }}
              className="mt-4 flex items-stretch gap-2 h-12"
              data-testid="vibe-form"
            >
              <input
                value={vibe}
                onChange={(e) => setVibe(e.target.value)}
                placeholder="e.g. cozy minimalist home, y2k glam, gamer desk setup…"
                className="flex-1 h-full px-4 rounded-full border-2 border-[#FF7A18]/60 focus:border-[#FF7A18] bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 focus:outline-none"
                data-testid="vibe-input"
                autoComplete="off"
              />
              <button
                type="submit"
                disabled={loading || vibe.trim().length < 2}
                className="h-full px-5 rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm shadow-sm transition flex items-center gap-2"
                data-testid="vibe-submit"
              >
                {loading ? (<><Loader2 className="h-4 w-4 animate-spin" /> Reading the vibe…</>) : (<><Sparkles className="h-4 w-4" /> Find my vibe</>)}
              </button>
              {result && !loading && (
                <button
                  type="button"
                  onClick={clearAll}
                  aria-label="Clear vibe"
                  className="h-full px-4 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF211F] text-neutral-700 dark:text-neutral-200 transition flex items-center gap-1"
                  data-testid="vibe-clear"
                >
                  <X className="h-4 w-4" /> Clear
                </button>
              )}
            </form>

            {/* Example chips */}
            {!result && !loading && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="text-[11px] text-neutral-500 dark:text-neutral-400 mr-1 self-center">Try:</span>
                {VIBE_EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => { setVibe(ex); runVibe(ex); }}
                    className="px-3 h-7 rounded-full bg-white dark:bg-neutral-800 hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817] border border-neutral-200 dark:border-neutral-700 text-xs text-neutral-700 dark:text-neutral-200 hover:text-[#FF211F] hover:border-[#FF7A18]/40 transition"
                    data-testid={`vibe-example-${ex.replace(/\s+/g, '-')}`}
                  >
                    {ex}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="mt-4 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm px-4 py-2.5" data-testid="vibe-error">
            {error}
          </div>
        )}
      </div>

      {/* Result interpretation & items */}
      {result && (
        <div className="mt-6" data-testid="vibe-results">
          <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5">
            <div className="flex items-start gap-2">
              <Sparkles className="h-4 w-4 mt-0.5 text-[#FF7A18] shrink-0" />
              <div className="min-w-0">
                <div className="text-sm text-neutral-900 dark:text-neutral-100" data-testid="vibe-explanation">
                  <span className="text-neutral-500 dark:text-neutral-400">Vibe read:</span>{" "}
                  <span className="font-medium">{result.explanation || `"${result.vibe}"`}</span>
                </div>
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  {result.categories?.map((c) => (
                    <Link
                      key={c.id}
                      to={`/search?category=${c.id}`}
                      className="px-2.5 h-6 rounded-full bg-[#FF7A18]/10 text-[#FF211F] text-[11px] font-semibold hover:bg-[#FF7A18]/20 transition inline-flex items-center"
                      data-testid={`vibe-cat-${c.slug}`}
                    >
                      {c.name}
                    </Link>
                  ))}
                  {result.keywords?.map((k) => (
                    <span
                      key={k}
                      className="px-2.5 h-6 rounded-full bg-neutral-100 dark:bg-neutral-800 text-[11px] text-neutral-700 dark:text-neutral-200 inline-flex items-center"
                    >
                      {k}
                    </span>
                  ))}
                  {result.brand_hints?.map((b) => (
                    <span
                      key={b}
                      className="px-2.5 h-6 rounded-full border border-neutral-200 dark:border-neutral-700 text-[11px] text-neutral-600 dark:text-neutral-300 inline-flex items-center"
                    >
                      {b}
                    </span>
                  ))}
                  {result.fallback && result.fallback !== "strict" && (
                    <span className="px-2.5 h-6 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 text-[11px] font-medium inline-flex items-center" title="We broadened the filter to find more matches">
                      broadened
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {result.items?.length === 0 ? (
            <div className="mt-6 text-center py-12 rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700">
              <p className="text-neutral-500 dark:text-neutral-400">No matches for this vibe yet. Try something simpler.</p>
            </div>
          ) : (
            <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" data-testid="vibe-items-grid">
              {result.items.map((l) => (
                <ProductCard key={l.id} listing={l} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VibeSearch;
