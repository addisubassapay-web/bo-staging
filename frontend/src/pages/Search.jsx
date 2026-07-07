import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { SlidersHorizontal, X } from "lucide-react";

const Search = () => {
  const [params, setParams] = useSearchParams();
  const [categories, setCategories] = useState([]);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [favIds, setFavIds] = useState(new Set());
  const [showFilters, setShowFilters] = useState(false);

  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const condition = params.get("condition") || "";
  const sort = params.get("sort") || "newest";
  const min = params.get("min") || "";
  const max = params.get("max") || "";

  const [priceRange, setPriceRange] = useState([Number(min) || 0, Number(max) || 500]);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data)).catch(() => {});
    const token = localStorage.getItem("mercari_token");
    if (token) api.get("/favorites").then((r) => setFavIds(new Set(r.data.map((l) => l.id)))).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const query = { sort, limit: 60 };
    if (q) query.q = q;
    if (category) query.category_id = category;
    if (condition) query.condition = condition;
    if (min) query.min_price = Number(min);
    if (max) query.max_price = Number(max);
    api.get("/listings", { params: query })
      .then((r) => setListings(r.data))
      .catch(() => setListings([]))
      .finally(() => setLoading(false));
  }, [q, category, condition, sort, min, max]);

  const updateParam = (key, val) => {
    const next = new URLSearchParams(params);
    if (val === "" || val === null || val === undefined) next.delete(key);
    else next.set(key, val);
    setParams(next);
  };

  const clearAll = () => setParams({});

  const activeFilters = [category, condition, min, max].filter(Boolean).length + (q ? 1 : 0);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900">
            {q ? `Results for "${q}"` : "Shop all"}
          </h1>
          <p className="text-sm text-neutral-500 mt-1">{listings.length} items</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="md:hidden" onClick={() => setShowFilters((v) => !v)}>
            <SlidersHorizontal className="h-4 w-4 mr-2" /> Filters {activeFilters > 0 && `(${activeFilters})`}
          </Button>
          <Select value={sort} onValueChange={(v) => updateParam("sort", v)}>
            <SelectTrigger className="w-[180px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest first</SelectItem>
              <SelectItem value="price_asc">Price: low to high</SelectItem>
              <SelectItem value="price_desc">Price: high to low</SelectItem>
              <SelectItem value="popular">Most popular</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid md:grid-cols-[240px_1fr] gap-6">
        <aside className={`${showFilters ? "block" : "hidden"} md:block space-y-6`}>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Filters</h3>
            {activeFilters > 0 && (
              <button onClick={clearAll} className="text-xs text-[#FF211F] hover:underline flex items-center gap-1">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>

          <div>
            <h4 className="text-sm font-semibold mb-2">Category</h4>
            <div className="space-y-1 max-h-72 overflow-auto">
              <button
                onClick={() => updateParam("category", "")}
                className={`block w-full text-left px-2 py-1.5 rounded text-sm ${!category ? "bg-neutral-100 font-medium" : "hover:bg-neutral-50"}`}
              >
                All
              </button>
              {categories.map((c) => (
                <button
                  key={c.id}
                  onClick={() => updateParam("category", c.id)}
                  className={`block w-full text-left px-2 py-1.5 rounded text-sm ${category === c.id ? "bg-neutral-100 font-medium" : "hover:bg-neutral-50"}`}
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
                  key={v}
                  onClick={() => updateParam("condition", v)}
                  className={`block w-full text-left px-2 py-1.5 rounded text-sm ${condition === v ? "bg-neutral-100 font-medium" : "hover:bg-neutral-50"}`}
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
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="aspect-square bg-neutral-100 animate-pulse rounded-lg" />
              ))}
            </div>
          ) : listings.length === 0 ? (
            <div className="text-center py-20">
              <p className="text-neutral-500">No items found. Try adjusting filters.</p>
              <Button variant="outline" className="mt-4" onClick={clearAll}>Clear filters</Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {listings.map((l) => (
                <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default Search;
