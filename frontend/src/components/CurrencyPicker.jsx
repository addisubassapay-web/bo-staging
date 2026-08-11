import React, { useEffect, useRef, useState } from "react";
import { useCurrency, CURRENCY_LIST, currencyMeta } from "@/context/CurrencyContext";
import { ChevronDown } from "lucide-react";

const CurrencyPicker = () => {
  const { currency, setCurrency } = useCurrency();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const meta = currencyMeta(currency);

  useEffect(() => {
    const onOutside = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="h-8 px-2.5 inline-flex items-center gap-1 rounded-full hover:bg-white/10 dark:hover:bg-white/5 text-xs font-medium transition"
        data-testid="currency-picker-btn"
        aria-label="Choose currency"
      >
        <span className="tabular-nums">{meta.symbol} {currency}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-50 w-48 rounded-2xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-xl py-1.5"
          data-testid="currency-picker-menu"
        >
          {CURRENCY_LIST.map((c) => {
            const m = currencyMeta(c);
            const active = c === currency;
            return (
              <button
                key={c}
                onClick={() => { setCurrency(c); setOpen(false); }}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition text-left ${active ? "font-semibold text-[#FF7A18]" : "text-neutral-800 dark:text-neutral-100"}`}
                data-testid={`currency-option-${c}`}
              >
                <span className="text-base leading-none">{m.flag}</span>
                <span className="w-8 tabular-nums">{c}</span>
                <span className="text-neutral-500 dark:text-neutral-400 text-xs truncate">{m.name}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default CurrencyPicker;
