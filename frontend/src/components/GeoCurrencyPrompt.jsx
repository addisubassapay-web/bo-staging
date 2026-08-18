import React, { useEffect, useState } from "react";
import { detectRegionAndCurrency } from "@/lib/geoDetect";
import { useCurrency } from "@/context/CurrencyContext";
import { useLang } from "@/context/LanguageContext";
import { Button } from "@/components/ui/button";
import { Coins, X } from "lucide-react";

const DISMISS_KEY = "mrc_geo_currency_prompt_dismissed";

/**
 * First-visit floating banner that suggests switching to the local currency
 * detected from `navigator.languages`. Shown at most once per browser
 * (dismissal + acceptance both stored in localStorage).
 */
const GeoCurrencyPrompt = () => {
  const { currency, setCurrency } = useCurrency();
  const { t } = useLang();
  const [suggestion, setSuggestion] = useState(null);

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY)) return;
    } catch { /* ignore */ }
    const g = detectRegionAndCurrency();
    if (g.currency && g.currency !== currency) setSuggestion(g);
  }, [currency]);

  if (!suggestion) return null;

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
    setSuggestion(null);
  };
  const accept = () => {
    setCurrency(suggestion.currency);
    dismiss();
  };

  return (
    <div
      className="fixed bottom-4 right-4 left-4 sm:left-auto z-[70] max-w-sm rounded-2xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-2xl p-4"
      role="dialog"
      aria-live="polite"
      data-testid="geo-currency-prompt"
    >
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 text-white grid place-items-center shrink-0">
          <Coins className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold">
            {(t("geo.title") || "You're browsing from {country}").replace("{country}", suggestion.country)}
          </div>
          <div className="text-xs text-neutral-500 mt-1">
            {(t("geo.body") || "Switch prices to {ccy}?").replace("{ccy}", suggestion.currency)}
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={accept} className="bg-[#FF211F] hover:bg-[#e01d1b] h-8" data-testid="geo-accept-btn">
              {(t("geo.switch") || "Switch to {ccy}").replace("{ccy}", suggestion.currency)}
            </Button>
            <Button size="sm" variant="outline" onClick={dismiss} className="h-8" data-testid="geo-dismiss-btn">
              {t("geo.keep") || "Keep " + currency}
            </Button>
          </div>
        </div>
        <button onClick={dismiss} className="text-neutral-400 hover:text-neutral-700" aria-label="Dismiss" data-testid="geo-close-btn">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

export default GeoCurrencyPrompt;
