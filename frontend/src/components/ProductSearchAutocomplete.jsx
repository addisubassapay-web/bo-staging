import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Search as SearchIcon, Package, WandSparkles, X, Clock } from "lucide-react";

const RECENT_KEY = "merchari.products.recentSearches";
const RECENT_MAX = 5;

function readRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function pushRecent(q) {
  const clean = (q || "").trim();
  if (clean.length < 2) return;
  try {
    const cur = readRecent().filter((x) => x.toLowerCase() !== clean.toLowerCase());
    const next = [clean, ...cur].slice(0, RECENT_MAX);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent("merchari-recent-searches"));
  } catch {
    /* localStorage disabled — silent */
  }
}

function clearRecent() {
  try {
    localStorage.removeItem(RECENT_KEY);
    window.dispatchEvent(new CustomEvent("merchari-recent-searches"));
  } catch { /* noop */ }
}

/**
 * Debounced autocomplete input for /products.
 * Emits `onSelect(query)` when the user picks a product / term / correction.
 * Renders inline results, spelling corrections, and related terms.
 */
export default function ProductSearchAutocomplete({
  value,
  onChange,
  onSubmit,
  placeholder = "Search products…",
}) {
  const [suggest, setSuggest] = useState(null);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const [recent, setRecent] = useState(readRecent);
  const debounceRef = useRef(null);
  const boxRef = useRef(null);
  const abortRef = useRef(null);

  // Keep the recent list in sync when the user searches from another tab
  // OR our own commit() pushes a new entry.
  useEffect(() => {
    const refresh = () => setRecent(readRecent());
    window.addEventListener("storage", refresh);
    window.addEventListener("merchari-recent-searches", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("merchari-recent-searches", refresh);
    };
  }, []);

  // Debounced fetch
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const q = (value || "").trim();
    if (q.length < 2) {
      setSuggest(null);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      if (abortRef.current) abortRef.current.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const res = await api.get("/products/suggest", {
          params: { q, limit: 8 },
          signal: ctrl.signal,
        });
        setSuggest(res.data);
        setActiveIdx(-1);
      } catch {
        /* aborted or transient network — ignore */
      }
    }, 180);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value]);

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const flatItems = useMemo(() => {
    if (!suggest) return [];
    // Ordered navigation: correction → categories → terms → products
    const items = [];
    if (suggest.corrected) items.push({ kind: "correction", value: suggest.corrected });
    for (const c of suggest.categories || [])
      items.push({ kind: "category", value: c });
    for (const t of suggest.terms || []) items.push({ kind: "term", value: t });
    for (const p of suggest.products || []) items.push({ kind: "product", value: p });
    return items;
  }, [suggest]);

  const commit = useCallback(
    (query) => {
      onChange(query);
      pushRecent(query);
      setOpen(false);
      onSubmit(query);
    },
    [onChange, onSubmit],
  );

  const onKey = (e) => {
    if (!open || !flatItems.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(flatItems.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(-1, i - 1));
    } else if (e.key === "Enter") {
      if (activeIdx >= 0) {
        e.preventDefault();
        const it = flatItems[activeIdx];
        if (it.kind === "product") {
          window.location.href = `/products/${it.value.id}`;
        } else if (it.kind === "category") {
          onChange("");
          setOpen(false);
          onSubmit("", it.value.name);
        } else {
          commit(it.kind === "correction" ? it.value : it.value);
        }
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const highlight = (text, q) => {
    if (!q) return text;
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="bg-[#FFE9E0] text-neutral-900 rounded px-0.5">
          {text.slice(idx, idx + q.length)}
        </mark>
        {text.slice(idx + q.length)}
      </>
    );
  };

  return (
    <div className="relative" ref={boxRef} data-testid="products-search-autocomplete">
      <SearchIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" />
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
        placeholder={placeholder}
        className="pl-9 pr-9 h-10 w-72 rounded-full border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-sm outline-none focus:border-[#FF211F] focus:ring-2 focus:ring-[#FF211F]/30 transition"
        data-testid="products-search-input"
        autoComplete="off"
      />
      {value ? (
        <button
          type="button"
          onClick={() => {
            onChange("");
            setSuggest(null);
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700"
          aria-label="Clear search"
          data-testid="products-search-clear"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}

      {/* Recent-searches panel — shown when the input is empty and open */}
      {open && !value && recent.length > 0 ? (
        <div
          className="absolute z-30 mt-2 w-[420px] max-w-[92vw] bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl shadow-2xl overflow-hidden"
          data-testid="products-search-recent"
        >
          <div className="px-4 pt-3 pb-1 flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-wide text-neutral-500 flex items-center gap-1.5">
              <Clock className="h-3 w-3" /> Recent searches
            </div>
            <button
              type="button"
              onClick={() => {
                clearRecent();
                setRecent([]);
              }}
              className="text-[11px] text-neutral-500 hover:text-[#FF211F] font-medium"
              data-testid="products-search-recent-clear"
            >
              Clear
            </button>
          </div>
          <ul className="py-1">
            {recent.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  onClick={() => commit(q)}
                  className="w-full text-left px-4 py-2 text-sm text-neutral-800 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-800/60 flex items-center gap-2"
                  data-testid={`products-search-recent-${q.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`}
                >
                  <SearchIcon className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {open && suggest && (suggest.products?.length || suggest.corrected || suggest.terms?.length) ? (
        <div
          className="absolute z-30 mt-2 w-[420px] max-w-[92vw] bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl shadow-2xl overflow-hidden"
          data-testid="products-search-dropdown"
        >
          {/* Correction banner */}
          {suggest.corrected ? (
            <button
              type="button"
              onClick={() => commit(suggest.corrected)}
              onMouseEnter={() => setActiveIdx(0)}
              className={`w-full text-left px-4 py-3 border-b border-neutral-100 dark:border-neutral-800 flex items-center gap-2 text-sm ${
                activeIdx === 0 ? "bg-neutral-50 dark:bg-neutral-800/60" : ""
              }`}
              data-testid="products-search-correction"
            >
              <WandSparkles className="h-4 w-4 text-[#FF211F] shrink-0" />
              <span className="text-neutral-600 dark:text-neutral-300">
                Did you mean{" "}
                <span className="font-semibold text-[#FF211F]">
                  {suggest.corrected}
                </span>
                ?
              </span>
            </button>
          ) : null}

          {/* Category quick-jump */}
          {suggest.categories?.length ? (
            <div className="px-4 py-2 border-b border-neutral-100 dark:border-neutral-800">
              <div className="text-[10px] uppercase tracking-wide text-neutral-500 mb-1.5">
                Categories
              </div>
              <div className="flex flex-wrap gap-1.5">
                {suggest.categories.map((c) => (
                  <button
                    key={c.slug}
                    type="button"
                    onClick={() => {
                      onChange("");
                      setOpen(false);
                      onSubmit("", c.name);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-[#FF211F]/10 hover:text-[#FF211F] px-2.5 h-6 text-xs"
                    data-testid={`products-search-cat-${c.slug}`}
                  >
                    {c.name}
                    <span className="tabular-nums text-[10px] text-neutral-500">
                      {c.count.toLocaleString()}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {/* Related terms */}
          {suggest.terms?.length ? (
            <div className="px-4 py-2 border-b border-neutral-100 dark:border-neutral-800">
              <div className="text-[10px] uppercase tracking-wide text-neutral-500 mb-1.5">
                Related
              </div>
              <div className="flex flex-wrap gap-1.5">
                {suggest.terms.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => commit(t)}
                    className="rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-[#FF211F]/10 hover:text-[#FF211F] px-2.5 h-6 text-xs"
                    data-testid={`products-search-term-${t}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {/* Product results */}
          {suggest.products?.length ? (
            <ul className="max-h-80 overflow-y-auto py-1" data-testid="products-search-results">
              {suggest.products.map((p, i) => {
                const idx = flatItems.findIndex(
                  (f) => f.kind === "product" && f.value.id === p.id,
                );
                return (
                  <li key={p.id}>
                    <Link
                      to={`/products/${p.id}`}
                      onClick={() => setOpen(false)}
                      onMouseEnter={() => setActiveIdx(idx)}
                      className={`flex items-center gap-3 px-4 py-2 text-sm ${
                        activeIdx === idx ? "bg-neutral-50 dark:bg-neutral-800/60" : "hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
                      }`}
                      data-testid={`products-search-result-${p.id}`}
                    >
                      <div className="h-10 w-10 rounded-md bg-neutral-100 dark:bg-neutral-800 overflow-hidden shrink-0 grid place-items-center">
                        {p.images?.[0] ? (
                          <img
                            src={p.images[0]}
                            alt=""
                            className={`w-full h-full object-cover ${p.in_stock === false ? "grayscale-[50%]" : ""}`}
                          />
                        ) : (
                          <Package className="h-5 w-5 text-neutral-400" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="line-clamp-1 text-neutral-800 dark:text-neutral-100">
                          {highlight(p.title, suggest.corrected || value)}
                        </div>
                        <div className="text-[11px] text-neutral-500 flex items-center gap-1.5">
                          {p.category ? <span>{p.category}</span> : null}
                          {p.in_stock === false ? (
                            <>
                              <span>·</span>
                              <span className="text-amber-600">Unavailable</span>
                            </>
                          ) : null}
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-[#FF211F] tabular-nums shrink-0">
                        {p.in_stock === false ? "—" : `$${Number(p.price).toFixed(2)}`}
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            !suggest.corrected && (
              <div className="px-4 py-6 text-center text-sm text-neutral-500">
                No matches. Try a different keyword.
              </div>
            )
          )}

          {/* Show-all footer */}
          {value?.length >= 2 && suggest.products?.length ? (
            <button
              type="button"
              onClick={() => commit(value)}
              className="w-full text-center border-t border-neutral-100 dark:border-neutral-800 px-4 py-2.5 text-xs font-semibold text-[#FF211F] hover:bg-[#FF211F]/5"
              data-testid="products-search-show-all"
            >
              Show all results for &ldquo;{value}&rdquo; →
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
