import React, { useState, useRef, useEffect } from "react";
import { useLang, LANGUAGES } from "@/context/LanguageContext";
import { useCurrency, CURRENCY_LIST } from "@/context/CurrencyContext";
import { Globe, Coins, ChevronDown } from "lucide-react";

/**
 * Compact language + currency selector for the header TopStrip.
 * Two tiny dropdown buttons, keyboard/click accessible, mobile-first.
 */
const LangCurrencySwitcher = () => {
  const { lang, setLang } = useLang();
  const { currency, setCurrency } = useCurrency();
  const [openLang, setOpenLang] = useState(false);
  const [openCur, setOpenCur] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpenLang(false); setOpenCur(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const current = LANGUAGES.find((l) => l.code === lang) || LANGUAGES[0];

  return (
    <div ref={ref} className="flex items-center gap-1 shrink-0" data-testid="lang-currency-switcher">
      {/* Language */}
      <div className="relative">
        <button
          onClick={() => { setOpenLang((v) => !v); setOpenCur(false); }}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:text-white text-xs"
          aria-label="Change language"
          data-testid="lang-btn"
        >
          <Globe className="h-3 w-3" />
          <span className="hidden sm:inline">{current.flag}</span>
          <span className="uppercase font-semibold tracking-wider">{lang}</span>
          <ChevronDown className="h-3 w-3" />
        </button>
        {openLang && (
          <div className="absolute right-0 top-full mt-1 z-50 min-w-[10rem] max-h-72 overflow-y-auto rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-lg py-1 text-neutral-800 dark:text-neutral-200" data-testid="lang-menu">
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => { setLang(l.code); setOpenLang(false); }}
                className={`w-full text-left px-3 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 flex items-center gap-2 text-sm ${l.code === lang ? "font-semibold text-[#FF211F]" : ""}`}
                data-testid={`lang-opt-${l.code}`}
              >
                <span>{l.flag}</span>
                <span>{l.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Currency */}
      <div className="relative">
        <button
          onClick={() => { setOpenCur((v) => !v); setOpenLang(false); }}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:text-white text-xs"
          aria-label="Change currency"
          data-testid="currency-btn"
        >
          <Coins className="h-3 w-3" />
          <span className="uppercase font-semibold tracking-wider">{currency}</span>
          <ChevronDown className="h-3 w-3" />
        </button>
        {openCur && (
          <div className="absolute right-0 top-full mt-1 z-50 min-w-[10rem] max-h-72 overflow-y-auto rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-lg py-1 text-neutral-800 dark:text-neutral-200" data-testid="currency-menu">
            {CURRENCY_LIST.map((c) => (
              <button
                key={c}
                onClick={() => { setCurrency(c); setOpenCur(false); }}
                className={`w-full text-left px-3 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 text-sm ${c === currency ? "font-semibold text-[#FF211F]" : ""}`}
                data-testid={`currency-opt-${c}`}
              >
                <span className="font-mono tracking-wider">{c}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default LangCurrencySwitcher;
