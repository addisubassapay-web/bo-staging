import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Trash2, ShoppingBag } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { useToast } from "@/hooks/use-toast";

const Cart = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { format } = useCurrency();
  const { t } = useLang();
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/cart").then((r) => setItems(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [user, authLoading, navigate]);

  const remove = async (id) => {
    await api.delete(`/cart/${id}`);
    setItems((prev) => prev.filter((i) => i.id !== id));
    toast({ title: t("cart.removed") });
  };

  const subtotal = items.reduce((s, i) => s + i.price, 0);
  const shipping = items.reduce((s, i) => s + (i.shipping_paid_by === "buyer" ? 5.99 : 0), 0);

  if (loading) return <div className="max-w-4xl mx-auto px-4 py-8">Loading…</div>;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8" data-testid="cart-page">
      <div className="mb-8">
        <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
          {t("cart.kicker")}
        </span>
        <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">{t("cart.title")}</h1>
        {items.length > 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {items.length} {items.length === 1 ? t("cart.item") : t("cart.items")} {t("cart.readyToCheckout")}
          </p>
        )}
      </div>

      {items.length === 0 ? (
        <div className="text-center py-20 rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900" data-testid="cart-empty">
          <ShoppingBag className="h-12 w-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-3" />
          <p className="text-neutral-600 dark:text-neutral-300">{t("cart.emptyLong")}</p>
          <Link to="/search"><Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-11 px-6">{t("cta.startShopping")}</Button></Link>
        </div>
      ) : (
        <div className="grid lg:grid-cols-[1fr_360px] gap-8">
          <div className="space-y-3">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex gap-4 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:border-[#FF7A18]/40 hover:shadow-[0_10px_24px_-14px_rgba(255,33,31,0.2)] transition-all duration-300"
                data-testid={`cart-item-${item.id}`}
              >
                <Link to={`/listing/${item.id}`} className="h-24 w-24 rounded-xl overflow-hidden bg-neutral-100 dark:bg-neutral-800 shrink-0 ring-1 ring-black/[0.04] dark:ring-white/10">
                  <img src={item.images?.[0]} alt="" className="w-full h-full object-cover" />
                </Link>
                <div className="flex-1 min-w-0">
                  <Link to={`/listing/${item.id}`} className="font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-2 hover:text-[#FF211F] transition">{item.title}</Link>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{t("cart.soldBy")} {item.seller_name}</div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400">
                    {item.shipping_paid_by === "seller" ? t("cart.freeShipping") : `${t("cart.shippingLabel")} ${format(5.99)}`}
                  </div>
                </div>
                <div className="flex flex-col items-end justify-between">
                  <div className="font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(item.price)}</div>
                  <button
                    onClick={() => remove(item.id)}
                    className="text-neutral-400 hover:text-[#FF211F] transition"
                    aria-label="Remove from cart"
                    data-testid={`cart-remove-${item.id}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 h-fit shadow-[0_1px_2px_rgba(0,0,0,0.04)] lg:sticky lg:top-24" data-testid="order-summary">
            <h2 className="font-bold text-lg mb-4 text-neutral-900 dark:text-neutral-100">{t("cart.orderSummary")}</h2>
            <div className="space-y-2.5 text-sm">
              <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
                <span>{t("cart.subtotal")}</span>
                <span className="tabular-nums font-medium">{format(subtotal)}</span>
              </div>
              <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
                <span>{t("cart.shipping")}</span>
                <span className="tabular-nums font-medium">{format(shipping)}</span>
              </div>
              <div className="flex justify-between text-neutral-700 dark:text-neutral-300">
                <span>{t("cart.tax")}</span>
                <span className="text-neutral-500 dark:text-neutral-400 text-xs">{t("cart.taxNote")}</span>
              </div>
              <div className="h-px bg-neutral-200 dark:bg-neutral-800 my-3" />
              <div className="flex justify-between font-extrabold text-lg text-neutral-900 dark:text-neutral-100">
                <span>{t("cart.total")}</span>
                <span className="tabular-nums">{format(subtotal + shipping)}</span>
              </div>
            </div>
            <Button
              onClick={() => navigate(`/checkout/${items[0].id}`)}
              className="w-full mt-5 bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-11 shadow-lg shadow-[#FF211F]/20"
              data-testid="checkout-btn"
            >
              {t("cart.checkout")} ({items.length})
            </Button>
            <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-3 text-center">
              {t("cart.secureDemo")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default Cart;
