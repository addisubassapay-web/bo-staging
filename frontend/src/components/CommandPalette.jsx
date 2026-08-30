import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { useCurrency } from "@/context/CurrencyContext";
import {
  Search, Package, ShoppingCart, Heart, MessageSquare, Wallet, AlertCircle,
  Store, BarChart3, Users, Link as LinkIcon, ShieldCheck, Settings, User,
  ArrowRight, Command,
} from "lucide-react";

const PAGES = [
  { path: "/", label: "menu.home", Icon: Package },
  { path: "/search", label: "menu.browse", Icon: Search },
  { path: "/cart", label: "cart.viewCart", Icon: ShoppingCart },
  { path: "/favorites", label: "menu.favorites", Icon: Heart },
  { path: "/chat", label: "menu.messages", Icon: MessageSquare },
  { path: "/wallet", label: "menu.wallet", Icon: Wallet },
  { path: "/disputes", label: "menu.disputes", Icon: AlertCircle },
  { path: "/my/store", label: "menu.myStore", Icon: Store },
  { path: "/store/analytics", label: "menu.storeAnalytics", Icon: BarChart3 },
  { path: "/referrals", label: "menu.referrals", Icon: Users },
  { path: "/affiliate", label: "menu.affiliate", Icon: LinkIcon },
  { path: "/verify", label: "Verification", Icon: ShieldCheck, raw: true },
  { path: "/profile", label: "menu.profile", Icon: User },
  { path: "/admin", label: "menu.admin", Icon: Settings },
  { path: "/sell", label: "nav.sell", Icon: Package },
];

const CommandPalette = ({ open, onClose }) => {
  const navigate = useNavigate();
  const { t } = useLang();
  const { format } = useCurrency();
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setItems([]);
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  // Debounced product suggestions
  useEffect(() => {
    if (!open) return;
    const query = q.trim();
    if (query.length < 2) { setItems([]); return; }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/search/suggest", { params: { q: query, limit: 6 } });
        setItems(data.items || []);
      } catch { /* ignore */ }
    }, 180);
    return () => clearTimeout(timerRef.current);
  }, [q, open]);

  const filteredPages = PAGES.filter((p) => {
    const label = p.raw ? p.label : t(p.label);
    return !q || label.toLowerCase().includes(q.toLowerCase());
  }).slice(0, 8);

  const allRows = [
    ...filteredPages.map((p) => ({ kind: "page", ...p })),
    ...items.map((it) => ({ kind: "item", ...it })),
  ];

  const go = (row) => {
    onClose();
    if (row.kind === "item") navigate(`/listing/${row.id}`);
    else navigate(row.path);
  };

  const submitQuery = () => {
    if (!q.trim()) return;
    onClose();
    navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  const onKeyDown = (e) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, allRows.length - 1)); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); return; }
    if (e.key === "Enter") {
      e.preventDefault();
      if (allRows[active]) go(allRows[active]);
      else submitQuery();
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[10vh] px-4 animate-in fade-in duration-150"
      onClick={onClose}
      data-testid="command-palette"
    >
      <div
        className="w-full max-w-2xl rounded-3xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-100 dark:border-neutral-800">
          <Search className="h-5 w-5 text-neutral-400 shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
            onKeyDown={onKeyDown}
            placeholder={t("commandPalette.placeholder")}
            className="flex-1 bg-transparent focus:outline-none text-lg text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400"
            data-testid="command-palette-input"
            autoComplete="off"
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 h-6 rounded border border-neutral-200 dark:border-neutral-700 text-[10px] font-mono text-neutral-500 dark:text-neutral-400">ESC</kbd>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {filteredPages.length > 0 && (
            <div className="py-1.5">
              <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">{t("menu.mainPages")}</div>
              {filteredPages.map((p, idx) => {
                const active_ = idx === active;
                const Icon = p.Icon;
                return (
                  <button
                    key={p.path}
                    onClick={() => go({ kind: "page", ...p })}
                    onMouseEnter={() => setActive(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition ${active_ ? "bg-neutral-100 dark:bg-neutral-800" : "hover:bg-neutral-50 dark:hover:bg-neutral-800/60"}`}
                    data-testid={`cp-page-${p.path.replace(/\//g, "-")}`}
                  >
                    <span className="h-8 w-8 rounded-lg bg-[#1E40AF]/10 text-[#1E40AF] grid place-items-center shrink-0">
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="flex-1 text-sm text-neutral-900 dark:text-neutral-100">{p.raw ? p.label : t(p.label)}</span>
                    <ArrowRight className="h-4 w-4 text-neutral-400" />
                  </button>
                );
              })}
            </div>
          )}
          {items.length > 0 && (
            <div className="py-1.5 border-t border-neutral-100 dark:border-neutral-800">
              <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">Products</div>
              {items.map((it, i) => {
                const idx = filteredPages.length + i;
                const active_ = idx === active;
                return (
                  <button
                    key={it.id}
                    onClick={() => go({ kind: "item", ...it })}
                    onMouseEnter={() => setActive(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition ${active_ ? "bg-neutral-100 dark:bg-neutral-800" : "hover:bg-neutral-50 dark:hover:bg-neutral-800/60"}`}
                    data-testid={`cp-item-${it.id}`}
                  >
                    <img src={it.image} alt="" className="h-9 w-9 rounded-lg object-cover bg-neutral-100 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-neutral-900 dark:text-neutral-100 line-clamp-1">{it.title}</div>
                      <div className="text-xs text-neutral-500 dark:text-neutral-400">{it.brand || it.category_name}</div>
                    </div>
                    <div className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(it.price)}</div>
                  </button>
                );
              })}
            </div>
          )}
          {allRows.length === 0 && q.trim().length >= 2 && (
            <button
              onClick={submitQuery}
              className="w-full text-center py-6 text-sm text-[#1E40AF] hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817] font-semibold"
              data-testid="cp-see-all"
            >
              See all results for &ldquo;{q}&rdquo; →
            </button>
          )}
        </div>

        <div className="flex items-center gap-3 px-4 py-2 border-t border-neutral-100 dark:border-neutral-800 text-[11px] text-neutral-500 dark:text-neutral-400">
          <span className="flex items-center gap-1"><kbd className="px-1 h-4 rounded border border-neutral-200 dark:border-neutral-700 text-[10px] font-mono">↑↓</kbd> navigate</span>
          <span className="flex items-center gap-1"><kbd className="px-1 h-4 rounded border border-neutral-200 dark:border-neutral-700 text-[10px] font-mono">↵</kbd> open</span>
          <span className="ml-auto flex items-center gap-1"><Command className="h-3 w-3" /> Command palette</span>
        </div>
      </div>
    </div>
  );
};

/** Hook that owns global ⌘K / Ctrl+K keyboard shortcut for opening the palette. */
export const useCommandPaletteShortcut = (setOpen) => {
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
};

export default CommandPalette;
