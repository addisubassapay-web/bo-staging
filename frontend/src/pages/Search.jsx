import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { SlidersHorizontal, X, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Package, Wand2 } from "lucide-react";
import VibeSearch from "@/components/VibeSearch";

const PAGE_SIZES = [24, 48, 96];

const Search = () => {
  const [params, setParams] = useSearchParams();
  const [categories, setCategories] = useState([]);
  const [listings, setListings] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [favIds, setFavIds] = useState(new Set());
  const [showFilters, setShowFilters] = useState(false);

  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const condition = params.get("condition") || "";
  const sort = params.get("sort") || "newest";
  const min = params.get("min") || "";
  const max = params.get("max") || "";
  const page = Math.max(1, parseInt(params.get("page") || "1", 10) || 1);
  const rawSize = parseInt(params.get("size") || "24", 10);
  const size = PAGE_SIZES.includes(rawSize) ? rawSize : 24;

  const [priceRange, setPriceRange] = useState([Number(min) || 0, Number(max) || 500]);
  const [vibeMode, setVibeMode] = useState(false);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data)).catch(() => {});
    const token = localStorage.getItem("mercari_token");
    if (token) api.get("/favorites").then((r) => setFavIds(new Set(r.data.map((l) => l.id)))).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const base = {};
    if (q) base.q = q;
    if (category) base.category_id = category;
    if (condition) base.condition = condition;
    if (min) base.min_price = Number(min);
    if (max) base.max_price = Number(max);
    const listQuery = { ...base, sort, limit: size, skip: (page - 1) * size };

    Promise.all([
      api.get("/listings", { params: listQuery }).then((r) => r.data).catch(() => []),
      api.get("/listings/count", { params: base }).then((r) => r.data?.total ?? 0).catch(() => 0),
    ])
      .then(([items, count]) => {
        setListings(items);
        setTotal(count);
      })
      .finally(() => setLoading(false));
  }, [q, category, condition, sort, min, max, page, size]);

  // Reset to page 1 whenever filters (NOT page/size) change.
  // Deliberately excluding page/params/setParams from deps — including page
  // would re-trigger on every navigation and reset the user right back to 1.
  useEffect(() => {
    if (page !== 1) {
      const next = new URLSearchParams(params);
      next.set("page", "1");
      setParams(next, { replace: true });
    }
  }, [q, category, condition, min, max, sort]);

  const totalPages = Math.max(1, Math.ceil(total / size));
  const boundedPage = Math.min(page, totalPages);
  const firstIndex = total === 0 ? 0 : (boundedPage - 1) * size + 1;
  const lastIndex = Math.min(boundedPage * size, total);

  const updateParam = (key, val) => {
    const next = new URLSearchParams(params);
    if (val === "" || val === null || val === undefined) next.delete(key);
    else next.set(key, String(val));
    setParams(next);
  };

  const goToPage = (p) => {
    const target = Math.max(1, Math.min(totalPages, p));
    if (target === page) return;
    updateParam("page", target === 1 ? "" : target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const clearAll = () => setParams({});

  const activeFilters = [category, condition, min, max].filter(Boolean).length + (q ? 1 : 0);
  const categoryName = useMemo(
    () => categories.find((c) => c.id === category)?.name || "",
    [category, categories],
  );

  const pageWindow = useMemo(() => computePageWindow(boundedPage, totalPages), [boundedPage, totalPages]);

  const headerTitle = q
    ? `Results for "${q}"`
    : categoryName
      ? categoryName
      : "All products";

  return (
    <div className="max-w-7xl mx-auto px-3 sm:px-4 py-6" data-testid="search-page">
      {/* Vibe mode toggle */}
      <div className="mb-4 flex items-center justify-end">
        <button
          onClick={() => setVibeMode((v) => !v)}
          className={`inline-flex items-center gap-1.5 px-4 h-9 rounded-full text-xs font-semibold transition ${
            vibeMode
              ? "bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white shadow-sm"
              : "bg-neutral-100 hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100"
          }`}
          data-testid="vibe-mode-toggle"
        >
          <Wand2 className="h-3.5 w-3.5" />
          {vibeMode ? "Vibe search on" : "Try Vibe search"}
          <span className={`text-[9px] px-1.5 rounded-full ${vibeMode ? "bg-white/25" : "bg-[#FF7A18] text-white"}`}>AI</span>
        </button>
      </div>

      {vibeMode && <VibeSearch />}

      <div className="flex items-center justify-between gap-4 mb-8 flex-wrap">
        <div>
          <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
            {q ? "Search" : categoryName ? "Category" : "Catalog"}
          </span>
          <h1 className="mt-2 text-2xl sm:text-4xl font-extrabold text-neutral-900 dark:text-neutral-100 tracking-tight flex items-center gap-2">
            {headerTitle}
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1" data-testid="results-summary">
            {loading ? "Loading…" : total === 0
              ? "0 items"
              : `Showing ${firstIndex.toLocaleString()}–${lastIndex.toLocaleString()} of ${total.toLocaleString()} items`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="outline" size="sm" className="md:hidden" onClick={() => setShowFilters((v) => !v)}>
            <SlidersHorizontal className="h-4 w-4 mr-2" /> Filters {activeFilters > 0 && `(${activeFilters})`}
          </Button>
          <Select value={String(size)} onValueChange={(v) => updateParam("size", v === "24" ? "" : v)}>
            <SelectTrigger className="w-[130px]" data-testid="page-size-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {PAGE_SIZES.map((s) => (
                <SelectItem key={s} value={String(s)}>{s} per page</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={(v) => updateParam("sort", v)}>
            <SelectTrigger className="w-[180px]" data-testid="sort-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest first</SelectItem>
              <SelectItem value="price_asc">Price: low to high</SelectItem>
              <SelectItem value="price_desc">Price: high to low</SelectItem>
              <SelectItem value="popular">Most popular</SelectItem>
              <SelectItem value="trending">Trending</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid md:grid-cols-[240px_1fr] gap-6">
        <aside className={`${showFilters ? "block" : "hidden"} md:block space-y-6`}>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Filters</h3>
            {activeFilters > 0 && (
              <button onClick={clearAll} className="text-xs text-[#FF211F] hover:underline flex items-center gap-1" data-testid="clear-filters-btn">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>

          <div>
            <h4 className="text-sm font-semibold mb-2">Category</h4>
            <div className="space-y-1 max-h-72 overflow-auto">
              <button
                onClick={() => updateParam("category", "")}
                className={`block w-full text-left px-2 py-1.5 rounded text-sm ${!category ? "bg-neutral-100 dark:bg-neutral-800 font-medium" : "hover:bg-neutral-50 dark:hover:bg-neutral-900"}`}
                data-testid="filter-category-all"
              >
                All
              </button>
              {categories.map((c) => (
                <button
                  key={c.id}
                  onClick={() => updateParam("category", c.id)}
                  className={`block w-full text-left px-2 py-1.5 rounded text-sm ${category === c.id ? "bg-neutral-100 dark:bg-neutral-800 font-medium" : "hover:bg-neutral-50 dark:hover:bg-neutral-900"}`}
                  data-testid={`filter-category-${c.slug || c.id}`}
                >
                  {c.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-sm font-semibold mb-2">Condition</h4>
            <div className="space-y-1">
              {[
                ["", "Any"],
                ["new", "New"],
                ["like_new", "Like new"],
                ["good", "Good"],
                ["fair", "Fair"],
                ["poor", "Poor"],
              ].map(([v, label]) => (
                <button
                  key={v || "any"}
                  onClick={() => updateParam("condition", v)}
                  className={`block w-full text-left px-2 py-1.5 rounded text-sm ${condition === v ? "bg-neutral-100 dark:bg-neutral-800 font-medium" : "hover:bg-neutral-50 dark:hover:bg-neutral-900"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-sm font-semibold mb-3">Price range</h4>
            <div className="px-1">
              <Slider
                value={priceRange}
                onValueChange={setPriceRange}
                onValueCommit={(v) => {
                  updateParam("min", v[0] || "");
                  updateParam("max", v[1] || "");
                }}
                min={0}
                max={1000}
                step={5}
                className="my-4"
              />
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={priceRange[0]}
                  onChange={(e) => setPriceRange([Number(e.target.value), priceRange[1]])}
                  onBlur={() => updateParam("min", priceRange[0] || "")}
                  className="h-8 text-sm"
                />
                <span className="text-neutral-400">–</span>
                <Input
                  type="number"
                  value={priceRange[1]}
                  onChange={(e) => setPriceRange([priceRange[0], Number(e.target.value)])}
                  onBlur={() => updateParam("max", priceRange[1] || "")}
                  className="h-8 text-sm"
                />
              </div>
            </div>
          </div>
        </aside>

        <main>
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="aspect-square bg-neutral-100 dark:bg-neutral-800 animate-pulse rounded-lg" />
              ))}
            </div>
          ) : listings.length === 0 ? (
            <div className="text-center py-20" data-testid="no-results">
              <Package className="h-12 w-12 text-neutral-300 dark:text-neutral-600 mx-auto" />
              <p className="text-neutral-500 dark:text-neutral-400 mt-3">No items found. Try adjusting filters.</p>
              <Button variant="outline" className="mt-4" onClick={clearAll}>Clear filters</Button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" data-testid="listings-grid">
                {listings.map((l) => (
                  <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} />
                ))}
              </div>

              {totalPages > 1 && (
                <Pagination
                  page={boundedPage}
                  totalPages={totalPages}
                  pageWindow={pageWindow}
                  goToPage={goToPage}
                />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
};

function computePageWindow(current, total) {
  // Show first 2, last 2, and current ±2 so users can hop several pages
  // in one click without being stranded when total is large (e.g. 113).
  const siblings = 2;
  const boundary = 2;
  const window = new Set();
  for (let i = 1; i <= Math.min(boundary, total); i++) window.add(i);
  for (let i = Math.max(1, total - boundary + 1); i <= total; i++) window.add(i);
  for (let i = Math.max(1, current - siblings); i <= Math.min(total, current + siblings); i++) window.add(i);
  return Array.from(window)
    .filter((n) => n >= 1 && n <= total)
    .sort((a, b) => a - b);
}

const Pagination = ({ page, totalPages, pageWindow, goToPage }) => {
  const [jumpTo, setJumpTo] = React.useState("");
  const submitJump = (e) => {
    e.preventDefault();
    const n = parseInt(jumpTo, 10);
    if (!Number.isNaN(n)) goToPage(n);
    setJumpTo("");
  };
  const cls = (active, disabled) =>
    `h-10 min-w-10 sm:h-9 sm:min-w-9 px-2.5 rounded-md text-sm font-medium border transition inline-flex items-center justify-center gap-1 ${
      active
        ? "bg-[#FF211F] text-white border-[#FF211F] shadow-sm"
        : disabled
          ? "bg-neutral-50 dark:bg-neutral-900 text-neutral-300 dark:text-neutral-600 border-neutral-200 dark:border-neutral-800 cursor-not-allowed"
          : "bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-200 border-neutral-200 dark:border-neutral-800 hover:border-[#FF7A18]"
    }`;

  return (
    <nav
      className="mt-8 flex items-center justify-center gap-1.5 flex-wrap"
      aria-label="Pagination"
      data-testid="pagination"
    >
      <button className={cls(false, page === 1)} disabled={page === 1} onClick={() => goToPage(1)} aria-label="First page" data-testid="page-first">
        <ChevronsLeft className="h-4 w-4" />
      </button>
      <button className={cls(false, page === 1)} disabled={page === 1} onClick={() => goToPage(page - 1)} aria-label="Previous page" data-testid="page-prev">
        <ChevronLeft className="h-4 w-4" />
      </button>

      {pageWindow.map((n, i) => {
        const prev = pageWindow[i - 1];
        const gap = prev != null && n - prev > 1;
        return (
          <React.Fragment key={n}>
            {gap && <span className="px-1 text-neutral-400" aria-hidden>…</span>}
            <button
              className={cls(n === page, false)}
              onClick={() => goToPage(n)}
              aria-current={n === page ? "page" : undefined}
              data-testid={`page-${n}`}
            >
              {n}
            </button>
          </React.Fragment>
        );
      })}

      <button className={cls(false, page === totalPages)} disabled={page === totalPages} onClick={() => goToPage(page + 1)} aria-label="Next page" data-testid="page-next">
        <ChevronRight className="h-4 w-4" />
      </button>
      <button className={cls(false, page === totalPages)} disabled={page === totalPages} onClick={() => goToPage(totalPages)} aria-label="Last page" data-testid="page-last">
        <ChevronsRight className="h-4 w-4" />
      </button>

      {totalPages > 7 && (
        <form onSubmit={submitJump} className="w-full sm:w-auto sm:ml-2 mt-2 sm:mt-0 inline-flex items-center justify-center gap-2" data-testid="page-jump-form">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">Go to</span>
          <input
            type="number"
            min="1"
            max={totalPages}
            value={jumpTo}
            onChange={(e) => setJumpTo(e.target.value)}
            placeholder={`1-${totalPages}`}
            className="h-10 w-24 rounded-md border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-2 text-sm text-center focus:outline-none focus:ring-2 focus:ring-[#2563EB]/30 focus:border-[#2563EB] transition"
            data-testid="page-jump-input"
            aria-label="Jump to page"
            inputMode="numeric"
          />
          <button
            type="submit"
            className="h-10 px-4 rounded-md bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white text-xs font-semibold hover:brightness-110 transition min-h-[40px]"
            data-testid="page-jump-btn"
          >
            Go
          </button>
        </form>
      )}
    </nav>
  );
};

export default Search;
