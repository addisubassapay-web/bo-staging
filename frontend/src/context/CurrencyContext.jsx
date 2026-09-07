import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";

const CurrencyContext = createContext(null);

const FALLBACK_RATES = {
  base: "USD",
  rates: {
    USD: 1, EUR: 0.92, GBP: 0.78, JPY: 155, INR: 83.2, CAD: 1.36,
    AUD: 1.52, BRL: 5.05, MXN: 17.1, CNY: 7.18, KRW: 1345, SGD: 1.34, AED: 3.673,
  },
};

const CURRENCY_META = {
  USD: { symbol: "$", locale: "en-US", flag: "🇺🇸", name: "US Dollar" },
  EUR: { symbol: "€", locale: "de-DE", flag: "🇪🇺", name: "Euro" },
  GBP: { symbol: "£", locale: "en-GB", flag: "🇬🇧", name: "British Pound" },
  JPY: { symbol: "¥", locale: "ja-JP", flag: "🇯🇵", name: "Japanese Yen" },
  INR: { symbol: "₹", locale: "en-IN", flag: "🇮🇳", name: "Indian Rupee" },
  CAD: { symbol: "$", locale: "en-CA", flag: "🇨🇦", name: "Canadian Dollar" },
  AUD: { symbol: "$", locale: "en-AU", flag: "🇦🇺", name: "Australian Dollar" },
  BRL: { symbol: "R$", locale: "pt-BR", flag: "🇧🇷", name: "Brazilian Real" },
  MXN: { symbol: "$", locale: "es-MX", flag: "🇲🇽", name: "Mexican Peso" },
  CNY: { symbol: "¥", locale: "zh-CN", flag: "🇨🇳", name: "Chinese Yuan" },
  KRW: { symbol: "₩", locale: "ko-KR", flag: "🇰🇷", name: "South Korean Won" },
  SGD: { symbol: "$", locale: "en-SG", flag: "🇸🇬", name: "Singapore Dollar" },
  AED: { symbol: "د.إ", locale: "ar-AE", flag: "🇦🇪", name: "UAE Dirham" },
};

export const CURRENCY_LIST = Object.keys(CURRENCY_META);

export const CurrencyProvider = ({ children }) => {
  const [currency, setCurrencyState] = useState(() => {
    // Currency defaults to explicit user pick (localStorage) or USD.
    // We deliberately DO NOT auto-persist the geo-detected currency here so
    // that <GeoCurrencyPrompt/> can show the "You're browsing from X — switch
    // to Y?" banner on the very first visit and let the user confirm. Once
    // they accept or dismiss, the choice is persisted.
    try {
      const existing = localStorage.getItem("blueocean_currency");
      if (existing) return existing;
    } catch { /* ignore */ }
    return "USD";
  });
  const [rateData, setRateData] = useState(() => {
    // Warm-start from cached rates so first paint uses the freshest known
    // rate (avoids a flash of stale fallback numbers on subsequent visits).
    try {
      const cached = localStorage.getItem("blueocean_rates");
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed && parsed.rates) return parsed;
      }
    } catch { /* ignore */ }
    return FALLBACK_RATES;
  });

  useEffect(() => {
    api.get("/currency/rates").then((r) => {
      setRateData(r.data);
      // Cache to localStorage so `formatPrice` in api.js (and any other
      // non-context call site) can format with live rates too.
      try { localStorage.setItem("blueocean_rates", JSON.stringify(r.data)); } catch { /* ignore */ }
    }).catch(() => {});
  }, []);

  const setCurrency = useCallback((c) => {
    setCurrencyState(c);
    localStorage.setItem("blueocean_currency", c);
  }, []);

  const convert = useCallback(
    (usd) => {
      const rate = rateData?.rates?.[currency] ?? 1;
      return Number(usd || 0) * rate;
    },
    [rateData, currency],
  );

  const format = useCallback(
    (usd) => {
      const meta = CURRENCY_META[currency] || CURRENCY_META.USD;
      const value = convert(usd);
      try {
        return new Intl.NumberFormat(meta.locale, {
          style: "currency",
          currency,
          // Zero-decimal currencies per Intl standard.
          maximumFractionDigits: currency === "JPY" || currency === "KRW" ? 0 : 2,
        }).format(value);
      } catch {
        return `${meta.symbol}${value.toFixed(currency === "JPY" || currency === "KRW" ? 0 : 2)}`;
      }
    },
    [convert, currency],
  );

  const value = useMemo(
    () => ({ currency, setCurrency, rates: rateData?.rates || {}, format, convert, meta: CURRENCY_META[currency] || CURRENCY_META.USD }),
    [currency, setCurrency, rateData, format, convert],
  );

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>;
};

export const useCurrency = () => {
  const ctx = useContext(CurrencyContext);
  if (!ctx) throw new Error("useCurrency must be used within CurrencyProvider");
  return ctx;
};

export const currencyMeta = (code) => CURRENCY_META[code] || CURRENCY_META.USD;
