import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { Search, Package as PackageIcon, Award, Loader2, ArrowRight, ShieldCheck } from "lucide-react";

const BADGE_META = {
  new: { label: "New seller", color: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200" },
  bronze: { label: "Bronze", color: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200" },
  silver: { label: "Silver", color: "bg-neutral-200 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-100" },
  gold: { label: "Gold", color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-500/20 dark:text-yellow-200" },
  override: { label: "Admin cap", color: "bg-[#FF7A18]/15 text-[#FF211F]" },
};

/**
 * ResellFromCatalog — Sell-page tab that lets a seller pick any existing catalog
 * listing, apply a markup capped by their tier badge (or admin override), and
 * publish it as their own reseller listing via POST /api/listings/import.
 */
const ResellFromCatalog = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [info, setInfo] = useState(null); // { badge, applied, max_markup_pct, platform_fee_pct, ...}
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState(null); // { id, title, image, price, brand, category_name }
  const [markup, setMarkup] = useState(20);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/seller/resell-info").then((r) => setInfo(r.data)).catch(() => {});
  }, []);

  // Debounced suggestions
  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) { setResults([]); return; }
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get("/search/suggest", { params: { q: query, limit: 8 } });
        setResults(data.items || []);
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 200);
    return () => clearTimeout(timer);
  }, [q]);

  const maxMk = Number(info?.max_markup_pct ?? 25);
  const cappedMarkup = Math.min(Math.max(0, Number(markup) || 0), maxMk);
  const overCap = Number(markup) > maxMk;

  const preview = useMemo(() => {
    if (!picked || !info) return null;
    const base = Number(picked.price) || 0;
    const salePrice = +(base * (1 + cappedMarkup / 100)).toFixed(2);
    const feePct = Number(info.platform_fee_pct ?? 8);
    const platformFee = +(salePrice * feePct / 100).toFixed(2);
    const sourceEarnings = base;
    const yours = Math.max(0, +(salePrice - platformFee - sourceEarnings).toFixed(2));
    const marginPct = salePrice > 0 ? +((yours / salePrice) * 100).toFixed(1) : 0;
    return { base, salePrice, platformFee, sourceEarnings, yours, marginPct, feePct };
  }, [picked, cappedMarkup, info]);

  const doPublish = async () => {
    if (!picked) { toast({ title: "Pick a product first", variant: "destructive" }); return; }
    if (overCap) return;
    setSubmitting(true);
    try {
      const { data } = await api.post("/listings/import", { listing_id: picked.id, markup_pct: cappedMarkup });
      toast({ title: "Listed as reseller!", description: `You'll earn ${formatPrice(preview.yours)} per sale.` });
      navigate(`/listing/${data.id}`);
    } catch (err) {
      toast({ title: "Could not publish", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const badgeMeta = BADGE_META[info?.applied] || BADGE_META.new;

  return (
    <div className="mt-6 space-y-6" data-testid="resell-panel">
      {/* Badge + cap */}
      {info && (
        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-gradient-to-br from-white to-neutral-50 dark:from-neutral-900 dark:to-neutral-950 p-4 sm:p-5" data-testid="resell-badge-card">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${badgeMeta.color}`}>
              <Award className="h-3.5 w-3.5" /> {badgeMeta.label} tier
            </span>
            <span className="text-sm text-neutral-600 dark:text-neutral-300">
              Max markup: <span className="font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">{maxMk}%</span>
            </span>
            <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-auto flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5" /> {info.sales_count} sales · {info.rating.toFixed(1)}★</span>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
            {info.override_active
              ? "An admin has set a personal cap for your account."
              : "Your cap grows automatically as you complete more sales with high ratings."}
          </p>
        </div>
      )}

      {/* Search products to resell */}
      <div>
        <Label className="text-base font-semibold">Pick a product to resell</Label>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-2">Search the catalog — the original seller fulfills, you keep the markup.</p>
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

        {results.length > 0 && !picked && (
          <ul className="mt-2 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden max-h-80 overflow-y-auto" data-testid="resell-results">
            {results.map((it) => (
              <li key={it.id}>
                <button
                  type="button"
                  onClick={() => setPicked(it)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-neutral-50 dark:hover:bg-neutral-800 text-left transition"
                  data-testid={`resell-pick-${it.id}`}
                >
                  <img src={it.image} alt="" className="h-12 w-12 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-neutral-900 dark:text-neutral-100 line-clamp-1">{it.title}</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">{it.brand || it.category_name}</div>
                  </div>
                  <div className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 tabular-nums shrink-0">{formatPrice(it.price)}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Picked product + markup */}
      {picked && (
        <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5" data-testid="resell-picked-card">
          <div className="flex items-start gap-3">
            <img src={picked.image} alt="" className="h-16 w-16 sm:h-20 sm:w-20 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">Source listing</div>
              <div className="font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-2">{picked.title}</div>
              <div className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">Base price {formatPrice(picked.price)} · {picked.brand || picked.category_name}</div>
            </div>
            <button
              type="button"
              onClick={() => setPicked(null)}
              className="text-xs text-neutral-500 hover:text-[#FF211F] transition"
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
              min={0}
              max={maxMk}
              value={markup}
              onChange={(e) => setMarkup(e.target.value)}
              className={`h-11 ${overCap ? "border-red-500 focus-visible:ring-red-500" : ""}`}
              data-testid="resell-markup-input"
            />
            <div className="mt-2 flex gap-1.5">
              {[5, 10, 20, 35, 50].filter((v) => v <= maxMk).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setMarkup(v)}
                  className={`px-3 h-7 rounded-full text-xs font-semibold transition ${Number(markup) === v ? "bg-[#FF211F] text-white" : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-neutral-700"}`}
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
                <span>Original seller price</span>
                <span className="tabular-nums font-medium">{formatPrice(preview.base)}</span>
              </div>
              <div className="flex justify-between text-[#FF7A18]">
                <span>Your markup (+{cappedMarkup}%)</span>
                <span className="tabular-nums font-semibold">+{formatPrice(preview.salePrice - preview.base)}</span>
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
                <span>Paid to original seller</span>
                <span className="tabular-nums">−{formatPrice(preview.sourceEarnings)}</span>
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

          <div className="mt-5 flex items-center justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setPicked(null)}>Cancel</Button>
            <Button
              type="button"
              onClick={doPublish}
              disabled={submitting || overCap || !preview || preview.yours <= 0}
              className="bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white gap-1.5"
              data-testid="resell-publish-btn"
            >
              {submitting ? "Publishing…" : (
                <>
                  Publish reseller listing <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {!picked && results.length === 0 && q.trim().length < 2 && (
        <div className="rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 p-8 text-center text-sm text-neutral-500 dark:text-neutral-400" data-testid="resell-empty">
          <PackageIcon className="h-8 w-8 mx-auto text-neutral-300 mb-2" />
          Start typing to browse the catalog. Pick any product to resell it in your store with a markup.
        </div>
      )}
    </div>
  );
};

export default ResellFromCatalog;
