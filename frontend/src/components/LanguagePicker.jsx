import React, { useEffect, useRef, useState } from "react";
import { useLang, LANGUAGES } from "@/context/LanguageContext";
import { ChevronDown, Globe } from "lucide-react";

const LanguagePicker = ({ variant = "compact" }) => {
  const { lang, setLang } = useLang();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const active = LANGUAGES.find((l) => l.code === lang) || LANGUAGES[0];

  useEffect(() => {
    const onOutside = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  const btnCls = variant === "prominent"
    ? "h-10 sm:h-11 px-3 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#2563EB] bg-white dark:bg-neutral-900 text-neutral-800 dark:text-neutral-100 text-sm font-medium transition inline-flex items-center gap-1.5"
    : "h-8 px-2.5 inline-flex items-center gap-1 rounded-full hover:bg-white/10 dark:hover:bg-white/5 text-xs font-medium transition";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={btnCls}
        data-testid="lang-picker-btn"
        aria-label="Choose language"
      >
        <Globe className="h-3.5 w-3.5" />
        <span>{active.flag} {active.code.toUpperCase()}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-50 w-48 rounded-2xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-xl py-1.5"
          data-testid="lang-picker-menu"
        >
          {LANGUAGES.map((l) => {
            const activeItem = l.code === lang;
            return (
              <button
                key={l.code}
                onClick={() => { setLang(l.code); setOpen(false); }}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition text-left ${activeItem ? "font-semibold text-[#5459E8]" : "text-neutral-800 dark:text-neutral-100"}`}
                data-testid={`lang-option-${l.code}`}
              >
                <span className="text-base leading-none">{l.flag}</span>
                <span className="w-8 tabular-nums uppercase">{l.code}</span>
                <span className="text-neutral-500 dark:text-neutral-400 text-xs truncate">{l.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default LanguagePicker;
