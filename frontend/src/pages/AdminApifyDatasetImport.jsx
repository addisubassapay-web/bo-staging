import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  Database,
  Download,
  CheckCircle2,
  AlertCircle,
  Package,
  ArrowRight,
  Info,
} from "lucide-react";

/**
 * AdminApifyDatasetImport — a single-shot form that ingests one Apify
 * dataset (by ID) into the permanent products catalog under a chosen
 * category + optional subcategory.
 *
 * Wraps `POST /api/admin/apify/datasets/{dataset_id}/import`.
 */
const AdminApifyDatasetImport = () => {
  const { toast } = useToast();
  const [datasetId, setDatasetId] = useState("");
  const [category, setCategory] = useState("");
  const [subcategory, setSubcategory] = useState("");
  const [maxItems, setMaxItems] = useState(5000);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/categories");
        setCategories(Array.isArray(data) ? data : []);
      } catch {
        // silent — free-form fallback still works
      }
    })();
  }, []);

  const canSubmit = datasetId.trim().length >= 6 && category.trim().length >= 1 && !loading;

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setResult(null);
    try {
      const params = new URLSearchParams({
        category: category.trim(),
        max_items: String(maxItems || 5000),
      });
      if (subcategory.trim()) params.set("subcategory", subcategory.trim());
      const { data } = await api.post(
        `/admin/apify/datasets/${encodeURIComponent(datasetId.trim())}/import?${params.toString()}`,
      );
      setResult(data);
      const c = data.created || 0;
      const u = data.updated || 0;
      const s = data.skipped || 0;
      toast({
        title: "Import finished",
        description: `+${c} created · ${u} updated · ${s} skipped`,
      });
    } catch (err) {
      toast({
        title: "Import failed",
        description: err?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-apify-dataset-import-page">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Database className="h-6 w-6" /> Direct dataset import
        </h2>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1 max-w-2xl">
          Paste an Apify dataset ID (found in the Apify console under Storage →
          Dataset), pick a target category, and we&apos;ll ingest every item into
          the permanent catalog. Prices are auto-converted to USD; images are
          rehosted in the background.
        </p>
      </div>

      {/* Info banner */}
      <div className="rounded-xl border border-sky-200 bg-sky-50 dark:border-sky-900/50 dark:bg-sky-950/30 p-3 flex gap-2">
        <Info className="h-5 w-5 text-sky-600 dark:text-sky-400 shrink-0 mt-0.5" />
        <div className="text-sm text-sky-800 dark:text-sky-200">
          Supported source shapes: Amazon / P2P marketplace / Flipkart-Shopsy
          <code className="text-[11px] bg-white/60 dark:bg-black/30 px-1 rounded mx-1">
            ProductSummaryValue
          </code>
          and generic products. Non-USD prices (INR, EUR, GBP, JPY, etc.) are
          converted at ingest time.
        </div>
      </div>

      {/* Form */}
      <form
        onSubmit={submit}
        className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 space-y-4"
        data-testid="apify-dataset-form"
      >
        <div>
          <Label htmlFor="ai-dataset-id">Dataset ID</Label>
          <Input
            id="ai-dataset-id"
            placeholder="e.g. 5P9IEkxZRt7Vpti00"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="mt-1 font-mono"
            required
            data-testid="ai-dataset-id-input"
          />
          <p className="text-xs text-neutral-500 mt-1">
            Copy from the Apify console → Storage tab → Dataset ID.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <Label htmlFor="ai-category">Category *</Label>
            {categories.length > 0 ? (
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger
                  id="ai-category"
                  className="mt-1"
                  data-testid="ai-category-select"
                >
                  <SelectValue placeholder="Pick a category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id || c.name} value={c.name}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                id="ai-category"
                placeholder="Men, Women, Electronics…"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                required
                className="mt-1"
                data-testid="ai-category-input"
              />
            )}
          </div>

          <div>
            <Label htmlFor="ai-subcat">Subcategory (optional)</Label>
            <Input
              id="ai-subcat"
              placeholder="Jeans, Leather wallet, Shirts…"
              value={subcategory}
              onChange={(e) => setSubcategory(e.target.value)}
              className="mt-1"
              data-testid="ai-subcat-input"
            />
          </div>
        </div>

        <div>
          <Label htmlFor="ai-max">Max items to fetch</Label>
          <Input
            id="ai-max"
            type="number"
            min={1}
            max={20000}
            value={maxItems}
            onChange={(e) => setMaxItems(Number(e.target.value) || 5000)}
            className="mt-1 max-w-[180px]"
            data-testid="ai-max-input"
          />
        </div>

        <Button
          type="submit"
          disabled={!canSubmit}
          className="w-full sm:w-auto bg-[#DC2626] hover:bg-[#e01d1b] min-h-[44px]"
          data-testid="ai-submit-btn"
        >
          {loading ? (
            <>
              <Download className="h-4 w-4 mr-2 animate-pulse" />
              Importing… this can take a minute
            </>
          ) : (
            <>
              <Download className="h-4 w-4 mr-2" />
              Import dataset
              <ArrowRight className="h-4 w-4 ml-2" />
            </>
          )}
        </Button>
      </form>

      {/* Result card */}
      {result && (
        <div
          className="rounded-xl border border-emerald-200 bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/30 p-5"
          data-testid="ai-result-card"
        >
          <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-200 font-semibold">
            <CheckCircle2 className="h-5 w-5" /> Import complete
          </div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-xs text-neutral-500 uppercase">Received</div>
              <div className="text-xl font-bold" data-testid="ai-result-received">{result.received}</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 uppercase">Created</div>
              <div className="text-xl font-bold text-emerald-700" data-testid="ai-result-created">
                +{result.created}
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 uppercase">Updated</div>
              <div className="text-xl font-bold text-sky-700" data-testid="ai-result-updated">
                {result.updated}
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 uppercase">Skipped</div>
              <div
                className={`text-xl font-bold ${result.skipped ? "text-amber-700" : "text-neutral-500"}`}
                data-testid="ai-result-skipped"
              >
                {result.skipped}
              </div>
            </div>
          </div>
          <div className="mt-3 text-xs text-neutral-600 dark:text-neutral-400 space-y-0.5">
            <div>
              <Package className="h-3.5 w-3.5 inline mr-1" />
              Category: <span className="font-semibold">{result.breadcrumbs || result.category}</span>
            </div>
            <div className="font-mono">Dataset: {result.dataset_id}</div>
            {result.mirror && (
              <div>
                Storefront mirror: +{result.mirror.created} · {result.mirror.updated} refreshed
              </div>
            )}
          </div>
          {result.skipped > 0 && result.created === 0 && result.updated === 0 && (
            <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-950/30 p-3 text-sm text-amber-800 dark:text-amber-200 flex gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                Every item was skipped — the dataset shape wasn&apos;t recognised
                by the normalizer. Share a sample item with the dev team so we
                can add an adapter.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AdminApifyDatasetImport;
