import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  Search, Package as PackageIcon, Award, Loader2, ArrowRight, ShieldCheck,
  FolderTree, Sparkles, TrendingDown,
} from "lucide-react";
import { StorefrontShareDialog } from "@/components/StorefrontShare";

const BADGE_META = {
  new: { label: "New seller", color: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200" },
  bronze: { label: "Bronze", color: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200" },
  silver: { label: "Silver", color: "bg-neutral-200 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-100" },
  gold: { label: "Gold", color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-500/20 dark:text-yellow-200" },
  override: { label: "Admin cap", color: "bg-[#FF7A18]/15 text-[#FF211F]" },
};

const ProductRow = ({ p, picked, onSelect, wholesaleDiscount }) => {
  const isPicked = picked?.id === p.id;
  const img = p.image || p.images?.[0];
  const wsCost = +((Number(p.price) || 0) * (1 - wholesaleDiscount / 100)).toFixed(2);
  return (
    <li className={`flex items-center gap-3 p-3 border-b border-neutral-100 dark:border-neutral-800 last:border-b-0 ${isPicked ? "bg-[#FFF3F2] dark:bg-red-950/20" : ""}`} data-testid={`resell-row-${p.id}`}>
      <img src={img} alt="" className="h-14 w-14 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100 line-clamp-1">{p.title}</div>
        <div className="text-xs text-neutral-500 mt-0.5 flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-neutral-800 dark:text-neutral-200 tabular-nums">{formatPrice(p.price)}</span>
          {wholesaleDiscount > 0 && (
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
              · Wholesale {formatPrice(wsCost)} ({wholesaleDiscount}% off)
            </span>
          )}
        </div>
      </div>
      <Button
        size="sm"
        onClick={() => onSelect({ ...p, image: img })}
        className={`min-h-[44px] rounded-full shrink-0 ${isPicked ? "bg-emerald-600 hover:bg-emerald-700" : "bg-[#FF211F] hover:bg-[#e01d1b]"} text-white`}
        data-testid={`resell-select-${p.id}`}
      >
        {isPicked ? "Selected" : "Select"}
      </Button>
    </li>
  );
};

const ResellFromCatalog = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [info, setInfo] = useState(null);
  const [mode, setMode] = useState("category"); // 'category' | 'search'
  const [categories, setCategories] = useState([]);
  const [categoryId, setCategoryId] = useState("");
  const [catLoading, setCatLoading] = useState(false);
  const [catProducts, setCatProducts] = useState([]);
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState(null);
  const [markup, setMarkup] = useState(20);
  const [submitting, setSubmitting] = useState(false);
  const [publishedListing, setPublishedListing] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [myStoreSlug, setMyStoreSlug] = useState(null);

  useEffect(() => {
    api.get("/seller/resell-info").then((r) => setInfo(r.data)).catch(() => {});
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
    api.get("/my/store").then((r) => setMyStoreSlug(r.data?.slug || null)).catch(() => {});
  }, []);

  // Load products by category
  useEffect(() => {
    if (mode !== "category" || !categoryId) { setCatProducts([]); return; }
    let alive = true;
    setCatLoading(true);
    api
      .get("/listings", { params: { category_id: categoryId, limit: 40, sort: "popular" } })
      .then((r) => { if (alive) setCatProducts(r.data || []); })
      .catch(() => { if (alive) setCatProducts([]); })
      .finally(() => { if (alive) setCatLoading(false); });
    return () => { alive = false; };
  }, [mode, categoryId]);

  // Debounced search suggestions (search mode)
  useEffect(() => {
    if (mode !== "search") { setResults([]); return; }
    const query = q.trim();
    if (query.length < 2) { setResults([]); return; }
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get("/search/suggest", { params: { q: query, limit: 12 } });
        setResults(data.items || []);
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 200);
    return () => clearTimeout(timer);
  }, [q, mode]);

  const maxMk = Number(info?.max_markup_pct ?? 25);
  const wholesaleDiscount = Number(info?.wholesale_discount_pct ?? 0);
  const cappedMarkup = Math.min(Math.max(0, Number(markup) || 0), maxMk);
  const overCap = Number(markup) > maxMk;

  const preview = useMemo(() => {
    if (!picked || !info) return null;
    const retail = Number(picked.price) || 0;
    const wholesale = +(retail * (1 - wholesaleDiscount / 100)).toFixed(2);
    const salePrice = +(retail * (1 + cappedMarkup / 100)).toFixed(2);
    const feePct = Number(info.platform_fee_pct ?? 8);
    const platformFee = +(salePrice * feePct / 100).toFixed(2);
    const yours = Math.max(0, +(salePrice - platformFee - wholesale).toFixed(2));
    const marginPct = salePrice > 0 ? +((yours / salePrice) * 100).toFixed(1) : 0;
    return { retail, wholesale, salePrice, platformFee, yours, marginPct, feePct };
  }, [picked, cappedMarkup, wholesaleDiscount, info]);

  const doPublish = async () => {
    if (!picked) { toast({ title: "Pick a product first", variant: "destructive" }); return; }
    if (overCap) return;
    setSubmitting(true);
    try {
      const { data } = await api.post("/listings/import", { listing_id: picked.id, markup_pct: cappedMarkup });
      toast({ title: "Listed as reseller!", description: `You'll earn ${formatPrice(preview.yours)} per sale.` });
      setPublishedListing(data);
      setShareOpen(true);
    } catch (err) {
      toast({ title: "Could not publish", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const onShareClose = (open) => {
    setShareOpen(open);
    if (!open && publishedListing) {
      navigate(`/listing/${publishedListing.id}`);
    }
  };

  const badgeMeta = BADGE_META[info?.applied] || BADGE_META.new;

  return (
    <div className="mt-6 space-y-6" data-testid="resell-panel">
      {/* Badge + wholesale card */}
      {info && (
        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-gradient-to-br from-white to-neutral-50 dark:from-neutral-900 dark:to-neutral-950 p-4 sm:p-5" data-testid="resell-badge-card">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${badgeMeta.color}`}>
              <Award className="h-3.5 w-3.5" /> {badgeMeta.label} tier
            </span>
            <span className="text-sm text-neutral-600 dark:text-neutral-300">
              Max markup: <span className="font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">{maxMk}%</span>
            </span>
            {wholesaleDiscount > 0 && (
              <span className="inline-flex items-center gap-1 text-xs bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 rounded-full px-2.5 py-1 font-medium">
                <TrendingDown className="h-3 w-3" /> {wholesaleDiscount}% wholesale discount
              </span>
            )}
            <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-auto flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5" /> {info.sales_count} sales · {info.rating.toFixed(1)}★</span>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
            {info.override_active
              ? "An admin has set a personal cap for your account."
              : "Your cap and wholesale discount grow automatically as you complete more sales with high ratings."}
          </p>
        </div>
      )}

      {/* Mode tabs */}
      <div className="inline-flex bg-neutral-100 dark:bg-neutral-800 rounded-full p-1 w-full sm:w-auto">
        <button
          type="button"
          onClick={() => { setMode("category"); setPicked(null); }}
          className={`flex-1 sm:flex-none min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === "category" ? "bg-white dark:bg-neutral-900 text-[#FF211F] shadow-sm" : "text-neutral-700 dark:text-neutral-300"}`}
          data-testid="resell-mode-category"
        >
          <FolderTree className="h-4 w-4" /> By category
        </button>
        <button
          type="button"
          onClick={() => { setMode("search"); setPicked(null); }}
          className={`flex-1 sm:flex-none min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === "search" ? "bg-white dark:bg-neutral-900 text-[#FF211F] shadow-sm" : "text-neutral-700 dark:text-neutral-300"}`}
          data-testid="resell-mode-search"
        >
          <Search className="h-4 w-4" /> Search
        </button>
      </div>

      {/* Category mode */}
      {mode === "category" && (
        <div className="space-y-3">
          <div>
            <Label className="text-base font-semibold">Choose a category</Label>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-2">Browse popular products — hit <b>Select</b> to preview earnings and publish.</p>
            <Select value={categoryId} onValueChange={setCategoryId}>
              <SelectTrigger className="h-11" data-testid="resell-category-select">
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                {categories.map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {categoryId && (
            <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden" data-testid="resell-category-products">
              {catLoading ? (
                <div className="p-10 flex flex-col items-center justify-center gap-2 text-sm text-neutral-500">
                  <Loader2 className="h-5 w-5 animate-spin" /> Loading products…
                </div>
              ) : catProducts.length === 0 ? (
                <div className="p-10 text-center text-sm text-neutral-500">No products found in this category yet.</div>
              ) : (
                <>
                  <div className="px-4 py-2 border-b border-neutral-100 dark:border-neutral-800 text-xs text-neutral-500 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5" /> {catProducts.length} products · sorted by popularity
                  </div>
                  <ul className="max-h-[440px] overflow-y-auto">
                    {catProducts.map((p) => <ProductRow key={p.id} p={p} picked={picked} onSelect={setPicked} wholesaleDiscount={wholesaleDiscount} />)}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Search mode */}
      {mode === "search" && (
        <div>
          <Label className="text-base font-semibold">Search a product</Label>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-2">Type to find any item — pick one to preview earnings.</p>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Try 'watch', 'sneakers', 'iphone case'…"
              className="pl-9 h-11"
              data-testid="resell-search-input"
            />
            {searching && <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-neutral-400" />}
          </div>

          {results.length > 0 && (
            <ul className="mt-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden max-h-96 overflow-y-auto" data-testid="resell-search-results">
              {results.map((it) => <ProductRow key={it.id} p={it} />)}
            </ul>
          )}
        </div>
      )}

      {/* Picked product + markup */}
      {picked && (
        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5" data-testid="resell-picked-card">
          <div className="flex items-start gap-3">
            <img src={picked.image} alt="" className="h-16 w-16 sm:h-20 sm:w-20 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">Source listing</div>
              <div className="font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-2">{picked.title}</div>
              <div className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">Retail {formatPrice(picked.price)} · {picked.brand || picked.category_name}</div>
            </div>
            <button
              type="button"
              onClick={() => setPicked(null)}
              className="min-h-[44px] px-2 text-xs text-neutral-500 hover:text-[#FF211F] transition"
              data-testid="resell-change-picked"
            >
              Change
            </button>
          </div>

          <div className="mt-5">
            <div className="flex items-center justify-between mb-1">
              <Label htmlFor="resell-markup">Your markup %</Label>
              <span className="text-[11px] text-neutral-500 dark:text-neutral-400">Max: {maxMk}%</span>
            </div>
            <Input
              id="resell-markup"
              type="number"
              inputMode="decimal"
              min={0}
              max={maxMk}
              value={markup}
              onChange={(e) => setMarkup(e.target.value)}
              className={`h-11 text-base ${overCap ? "border-red-500 focus-visible:ring-red-500" : ""}`}
              data-testid="resell-markup-input"
            />
            <div className="mt-2 flex gap-1.5 flex-wrap">
              {[5, 10, 20, 35, 50].filter((v) => v <= maxMk).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setMarkup(v)}
                  className={`min-h-[36px] px-3 rounded-full text-xs font-semibold transition ${Number(markup) === v ? "bg-[#FF211F] text-white" : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-neutral-700"}`}
                  data-testid={`resell-preset-${v}`}
                >
                  {v}%
                </button>
              ))}
            </div>
            {overCap && (
              <div className="mt-2 text-xs text-red-600 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-lg px-3 py-2">
                Your tier caps markup at {maxMk}%. Complete more sales with high ratings to level up.
              </div>
            )}
          </div>

          {/* Earnings preview */}
          {preview && (
            <div className="mt-5 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-gradient-to-br from-neutral-50 to-white dark:from-neutral-950 dark:to-neutral-900 p-4 space-y-1.5 text-sm" data-testid="resell-earnings-preview">
              <div className="flex justify-between text-neutral-600 dark:text-neutral-300">
                <span>Retail price</span>
                <span className="tabular-nums font-medium">{formatPrice(preview.retail)}</span>
              </div>
              <div className="flex justify-between text-emerald-600 dark:text-emerald-400">
                <span>Your wholesale cost ({wholesaleDiscount}% off)</span>
                <span className="tabular-nums font-semibold">{formatPrice(preview.wholesale)}</span>
              </div>
              <div className="flex justify-between text-[#FF7A18]">
                <span>Your markup (+{cappedMarkup}%)</span>
                <span className="tabular-nums font-semibold">+{formatPrice(preview.salePrice - preview.retail)}</span>
              </div>
              <div className="h-px bg-neutral-200 dark:bg-neutral-800 my-1.5" />
              <div className="flex justify-between text-neutral-900 dark:text-neutral-100 font-semibold">
                <span>Buyer pays</span>
                <span className="tabular-nums" data-testid="resell-sale-price">{formatPrice(preview.salePrice)}</span>
              </div>
              <div className="flex justify-between text-neutral-500">
                <span>Platform fee ({preview.feePct}%)</span>
                <span className="tabular-nums">−{formatPrice(preview.platformFee)}</span>
              </div>
              <div className="flex justify-between text-neutral-500">
                <span>Paid to original seller (wholesale)</span>
                <span className="tabular-nums">−{formatPrice(preview.wholesale)}</span>
              </div>
              <div className="h-px bg-neutral-200 dark:bg-neutral-800 my-1.5" />
              <div className="flex justify-between items-baseline">
                <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">You earn per sale</span>
                <div className="text-right">
                  <div className="text-xl font-extrabold text-emerald-600 tabular-nums" data-testid="resell-earn-amount">
                    {formatPrice(preview.yours)}
                  </div>
                  <div className="text-[11px] text-neutral-500 tabular-nums">{preview.marginPct}% margin · frozen until delivery</div>
                </div>
              </div>
            </div>
          )}

          <div className="mt-5 flex items-center justify-end gap-2 flex-col sm:flex-row">
            <Button type="button" variant="outline" onClick={() => setPicked(null)} className="min-h-[44px] w-full sm:w-auto">Cancel</Button>
            <Button
              type="button"
              onClick={doPublish}
              disabled={submitting || overCap || !preview || preview.yours <= 0}
              className="min-h-[44px] w-full sm:w-auto bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white gap-1.5"
              data-testid="resell-publish-btn"
            >
              {submitting ? "Publishing…" : (
                <>
                  Publish to my store <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {mode === "category" && !categoryId && !picked && (
        <div className="rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 p-8 text-center text-sm text-neutral-500 dark:text-neutral-400" data-testid="resell-empty">
          <PackageIcon className="h-8 w-8 mx-auto text-neutral-300 mb-2" />
          Choose a category above to browse products you can resell.
        </div>
      )}
      {mode === "search" && !picked && results.length === 0 && q.trim().length < 2 && (
        <div className="rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 p-8 text-center text-sm text-neutral-500 dark:text-neutral-400">
          <PackageIcon className="h-8 w-8 mx-auto text-neutral-300 mb-2" />
          Start typing to search the catalog.
        </div>
      )}

      <StorefrontShareDialog
        open={shareOpen}
        onOpenChange={onShareClose}
        listing={publishedListing}
        storeSlug={myStoreSlug}
        headline="Published! Share it to boost your first sale"
      />
    </div>
  );
};

export default ResellFromCatalog;
