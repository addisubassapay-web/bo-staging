import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Rocket, Loader2, Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const TIER_COPY = {
  bronze: { label: "Bronze", price: 5,  days: 7,  blurb: "1× boost score for a week." },
  silver: { label: "Silver", price: 12, days: 14, blurb: "2× boost score for two weeks — best value." },
  gold:   { label: "Gold",   price: 25, days: 30, blurb: "3× boost score for a full month." },
};

const BoostMyStore = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const [storeId, setStoreId] = useState(null);
  const [status, setStatus] = useState(null);
  const [categories, setCategories] = useState([]);
  const [tier, setTier] = useState("silver");
  const [categoryId, setCategoryId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user?.store_id) return;
    setStoreId(user.store_id);
    api.get(`/store-boost/status/${user.store_id}`).then((r) => setStatus(r.data)).catch(() => {});
    api.get("/categories").then((r) => setCategories(r.data || [])).catch(() => {});
  }, [user]);

  if (!user?.store_id) return null;

  const buy = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/store-boost/checkout", {
        store_id: storeId,
        tier,
        category_id: categoryId || null,
        origin_url: window.location.origin,
      });
      if (data?.checkout_url) window.location.href = data.checkout_url;
    } catch (e) {
      toast({ title: "Checkout failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setLoading(false); }
  };

  const active = status?.active_boosts || [];

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6" data-testid="boost-my-store-panel">
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-yellow-400 to-amber-500 text-white grid place-items-center shrink-0">
          <Rocket className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold">Boost my store to the top</h3>
          <p className="text-sm text-neutral-600 mt-1">
            Sponsor your storefront to the top of search results — globally or in a specific category. Higher tier = higher rank. Cancels automatically at the end of the term.
          </p>
        </div>
      </div>

      {active.length > 0 && (
        <div className="mt-4 rounded-xl bg-emerald-50/60 border border-emerald-200 p-3" data-testid="boost-active-list">
          <div className="text-xs font-semibold text-emerald-800 mb-1">Currently active</div>
          <div className="flex flex-wrap gap-1.5">
            {active.map((b) => (
              <Badge key={b.id} className="bg-emerald-100 text-emerald-800 border-none text-[11px]">
                {b.tier} · {b.category_id ? "category" : "global"} · until {new Date(b.expires_at).toLocaleDateString()}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        {Object.entries(TIER_COPY).map(([id, t]) => (
          <button
            key={id}
            onClick={() => setTier(id)}
            className={`text-start rounded-xl p-4 border-2 transition ${tier === id ? "border-[#DC2626] bg-[#FFF6F5]" : "border-neutral-200 hover:border-neutral-300"}`}
            data-testid={`boost-tier-${id}`}
          >
            <div className="flex items-center justify-between">
              <div className="font-bold flex items-center gap-1.5">
                {id === "gold" && <Sparkles className="h-4 w-4 text-yellow-500" />}
                {t.label}
              </div>
              <div className="tabular-nums font-bold">${t.price}</div>
            </div>
            <div className="text-xs text-neutral-600 mt-1">{t.blurb}</div>
            <div className="text-[11px] text-neutral-500 mt-2">{t.days}-day term</div>
          </button>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Scope</Label>
          <Select value={categoryId || "__all__"} onValueChange={(v) => setCategoryId(v === "__all__" ? "" : v)}>
            <SelectTrigger className="mt-1 h-10" data-testid="boost-scope-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Global (all storefront search)</SelectItem>
              {categories.map((c) => <SelectItem key={c.id} value={c.id}>Category: {c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end">
          <Button
            onClick={buy}
            disabled={loading}
            className="w-full h-10 bg-[#DC2626] hover:bg-[#e01d1b]"
            data-testid="boost-buy-btn"
          >
            {loading
              ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Redirecting…</>
              : <>Boost with {TIER_COPY[tier].label} — ${TIER_COPY[tier].price}</>}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default BoostMyStore;
