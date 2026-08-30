import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { ShoppingCart, X } from "lucide-react";

/**
 * MiniCart — hover-triggered cart flyout preview on the header cart icon.
 * Falls back to click-based on touch devices.
 */
const MiniCart = ({ cartCount, onCountChange }) => {
  const { user } = useAuth();
  const { format } = useCurrency();
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);
  const closeTimer = useRef(null);

  const load = () => {
    if (!user) return;
    setLoading(true);
    api.get("/cart").then((r) => setItems(r.data || [])).catch(() => setItems([])).finally(() => setLoading(false));
  };

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user]);

  useEffect(() => {
    const onOutside = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  const openIt = () => { clearTimeout(closeTimer.current); setOpen(true); };
  const closeIt = () => { closeTimer.current = setTimeout(() => setOpen(false), 200); };

  const subtotal = items.reduce((s, it) => s + Number(it.price || 0), 0);

  const removeItem = async (id) => {
    try {
      await api.delete(`/cart/${id}`);
      const next = items.filter((i) => i.id !== id);
      setItems(next);
      onCountChange?.(next.length);
    } catch { /* ignore */ }
  };

  return (
    <div ref={wrapRef} className="relative" onMouseEnter={openIt} onMouseLeave={closeIt}>
      <Link to="/cart" onClick={() => setOpen(false)}>
        <button
          aria-label="Cart"
          className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#5459E8] grid place-items-center transition relative text-neutral-700 dark:text-neutral-200"
          data-testid="header-cart-btn"
        >
          <ShoppingCart className="h-5 w-5" />
          {cartCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-[#DC2626] text-white text-[10px] font-semibold rounded-full h-4 min-w-4 px-1 grid place-items-center leading-none tabular-nums">
              {cartCount > 99 ? "99+" : cartCount}
            </span>
          )}
        </button>
      </Link>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 z-50 w-80 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-2xl overflow-hidden"
          data-testid="mini-cart-flyout"
          onMouseEnter={openIt}
          onMouseLeave={closeIt}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-100 dark:border-neutral-800">
            <div className="font-semibold text-neutral-900 dark:text-neutral-100">{t("cart.title")}</div>
            <span className="text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">{items.length} {items.length === 1 ? "item" : "items"}</span>
          </div>
          {!user ? (
            <div className="p-6 text-center text-sm text-neutral-500 dark:text-neutral-400">
              <Link to="/login" onClick={() => setOpen(false)} className="text-[#5459E8] font-semibold hover:underline">Sign in</Link> to see your cart.
            </div>
          ) : loading ? (
            <div className="p-6 text-center text-sm text-neutral-500 dark:text-neutral-400">Loading…</div>
          ) : items.length === 0 ? (
            <div className="p-6 text-center text-sm text-neutral-500 dark:text-neutral-400">{t("cart.empty")}</div>
          ) : (
            <>
              <ul className="max-h-72 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800">
                {items.slice(0, 6).map((it) => (
                  <li key={it.id} className="flex items-center gap-3 px-4 py-2.5" data-testid={`mini-cart-item-${it.id}`}>
                    <Link to={`/listing/${it.id}`} onClick={() => setOpen(false)} className="flex items-center gap-3 flex-1 min-w-0 hover:opacity-80">
                      <img src={it.images?.[0]} alt="" className="h-12 w-12 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-neutral-900 dark:text-neutral-100 line-clamp-1">{it.title}</div>
                        <div className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(it.price)}</div>
                      </div>
                    </Link>
                    <button
                      onClick={() => removeItem(it.id)}
                      aria-label="Remove"
                      className="h-7 w-7 rounded-full text-neutral-400 hover:text-[#DC2626] hover:bg-neutral-100 dark:hover:bg-neutral-800 grid place-items-center transition"
                      data-testid={`mini-cart-remove-${it.id}`}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="px-4 py-3 border-t border-neutral-100 dark:border-neutral-800">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">{t("cart.subtotal")}</span>
                  <span className="text-base font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums" data-testid="mini-cart-subtotal">{format(subtotal)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Link to="/cart" onClick={() => setOpen(false)} className="flex-1">
                    <button className="w-full h-10 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#5459E8] text-sm font-semibold text-neutral-800 dark:text-neutral-100 transition" data-testid="mini-cart-view-cart">
                      {t("cart.viewCart")}
                    </button>
                  </Link>
                  {items.length > 0 && (
                    <Link to={`/checkout/${items[0].id}`} onClick={() => setOpen(false)} className="flex-1">
                      <button className="w-full h-10 rounded-full bg-gradient-to-r from-[#5459E8] to-[#818CF8] hover:brightness-110 text-white text-sm font-semibold shadow-sm transition" data-testid="mini-cart-checkout">
                        {t("cart.checkout")}
                      </button>
                    </Link>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default MiniCart;
