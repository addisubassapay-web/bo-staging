import React, { useEffect, useState, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Package, Search as SearchIcon, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 24;

const formatMoney = (amount, currency = "USD") => {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `$${Number(amount).toFixed(2)}`;
  }
};

const ProductCardMini = ({ p }) => {
  const img = p.images?.[0];
  const oos = p.in_stock === false;
  return (
    <Link
      to={`/products/${p.id}`}
      className={`group bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl overflow-hidden hover:shadow-lg transition ${
        oos ? "opacity-90" : ""
      }`}
      data-testid={`product-card-${p.id}`}
      aria-label={oos ? `${p.title} — currently unavailable` : p.title}
    >
      <div className="relative aspect-square bg-neutral-100 dark:bg-neutral-800 overflow-hidden">
        {img ? (
          <img
            src={img}
            alt={p.title}
            loading="lazy"
            className={`w-full h-full object-cover group-hover:scale-105 transition ${
              oos ? "grayscale-[45%]" : ""
            }`}
          />
        ) : (
          <div className="w-full h-full grid place-items-center text-neutral-400">
            <Package className="h-10 w-10" />
          </div>
        )}
        {oos && (
          <>
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-neutral-900/25 to-transparent" />
            <span
              className="absolute top-2.5 left-2.5 inline-flex items-center gap-1.5 rounded-full bg-neutral-900/85 text-white text-[10px] font-bold uppercase tracking-wide px-2.5 py-1 shadow ring-1 ring-white/10 backdrop-blur"
              data-testid={`product-oos-badge-${p.id}`}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              Currently Unavailable
            </span>
          </>
        )}
      </div>
      <div className="p-3">
        <div className="text-sm text-neutral-900 dark:text-neutral-100 line-clamp-2 min-h-[2.5rem]">
          {p.title}
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          {oos ? (
            <span
              className="text-sm font-semibold text-neutral-500 dark:text-neutral-400"
              data-testid={`product-restock-hint-${p.id}`}
            >
              Restocking soon
            </span>
          ) : (
            <span className="text-lg font-bold text-[#FF211F]">
              {formatMoney(p.price, p.currency)}
            </span>
          )}
          {p.category ? (
            <span className="text-[10px] uppercase tracking-wide text-neutral-500">
              {p.category}
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  );
};

const Products = () => {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page") || 1));
  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const inStockOnly = params.get("in_stock") === "1";
  const [qDraft, setQDraft] = useState(q);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/products", {
        params: {
          page,
          page_size: PAGE_SIZE,
          ...(q ? { q } : {}),
          ...(category ? { category } : {}),
          ...(inStockOnly ? { in_stock_only: true } : {}),
        },
      });
      setData(res.data);
    } catch (err) {
      setData({ items: [], total: 0, page: 1, page_size: PAGE_SIZE });
    } finally {
      setLoading(false);
    }
  }, [page, q, category, inStockOnly]);

  useEffect(() => {
    load();
  }, [load]);

  const submitSearch = (e) => {
    e.preventDefault();
    const next = new URLSearchParams(params);
    if (qDraft) next.set("q", qDraft);
    else next.delete("q");
    next.set("page", "1");
    setParams(next);
  };

  const goPage = (n) => {
    const next = new URLSearchParams(params);
    next.set("page", String(n));
    setParams(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8" data-testid="products-catalog-page">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <Package className="h-6 w-6 text-[#FF211F]" />
            <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">
              Permanent Catalog
            </h1>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Curated products imported directly from our supply pipeline
            {data ? ` · ${data.total.toLocaleString()} products` : ""}
          </p>
        </div>
        <form onSubmit={submitSearch} className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300 select-none">
            <input
              type="checkbox"
              checked={inStockOnly}
              onChange={(e) => {
                const next = new URLSearchParams(params);
                if (e.target.checked) next.set("in_stock", "1");
                else next.delete("in_stock");
                next.set("page", "1");
                setParams(next);
              }}
              className="h-4 w-4 accent-[#FF211F]"
              data-testid="products-in-stock-only-toggle"
            />
            In stock only
          </label>
          <div className="relative">
            <SearchIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
            <Input
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
              placeholder="Search products…"
              className="pl-9 w-64"
              data-testid="products-search-input"
            />
          </div>
          <Button type="submit" className="bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="products-search-btn">
            Search
          </Button>
        </form>
      </div>

      {loading && !data ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-square bg-neutral-100 dark:bg-neutral-800 rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : data?.items.length ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="products-grid">
            {data.items.map((p) => (
              <ProductCardMini key={p.id} p={p} />
            ))}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-8" data-testid="products-pagination">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => goPage(page - 1)}
                data-testid="products-prev-btn"
              >
                <ChevronLeft className="h-4 w-4" /> Prev
              </Button>
              <span className="text-sm text-neutral-600 dark:text-neutral-300 px-3">
                Page {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => goPage(page + 1)}
                data-testid="products-next-btn"
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      ) : (
        <div
          className="text-center py-16 border border-dashed border-neutral-300 dark:border-neutral-700 rounded-2xl"
          data-testid="products-empty"
        >
          <Package className="h-12 w-12 text-neutral-300 mx-auto mb-3" />
          <p className="text-neutral-600 dark:text-neutral-300 font-medium">
            No products yet
          </p>
          <p className="text-sm text-neutral-500 mt-1">
            Products imported via the Apify webhook will appear here permanently.
          </p>
        </div>
      )}
    </div>
  );
};

export default Products;
