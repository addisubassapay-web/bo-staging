import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";

const CurrencyContext = createContext(null);

const FALLBACK_RATES = {
  base: "USD",
  rates: { USD: 1, EUR: 0.92, GBP: 0.78, JPY: 155, INR: 83.2, CAD: 1.36 },
};

const CURRENCY_META = {
  USD: { symbol: "$", locale: "en-US", flag: "🇺🇸", name: "US Dollar" },
  EUR: { symbol: "€", locale: "de-DE", flag: "🇪🇺", name: "Euro" },
  GBP: { symbol: "£", locale: "en-GB", flag: "🇬🇧", name: "British Pound" },
  JPY: { symbol: "¥", locale: "ja-JP", flag: "🇯🇵", name: "Japanese Yen" },
  INR: { symbol: "₹", locale: "en-IN", flag: "🇮🇳", name: "Indian Rupee" },
  CAD: { symbol: "$", locale: "en-CA", flag: "🇨🇦", name: "Canadian Dollar" },
};

export const CURRENCY_LIST = Object.keys(CURRENCY_META);

export const CurrencyProvider = ({ children }) => {
  const [currency, setCurrencyState] = useState(() => localStorage.getItem("mercari_currency") || "USD");
  const [rateData, setRateData] = useState(FALLBACK_RATES);

  useEffect(() => {
    api.get("/currency/rates").then((r) => setRateData(r.data)).catch(() => {});
  }, []);

  const setCurrency = useCallback((c) => {
    setCurrencyState(c);
    localStorage.setItem("mercari_currency", c);
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
          maximumFractionDigits: currency === "JPY" ? 0 : 2,
        }).format(value);
      } catch {
        return `${meta.symbol}${value.toFixed(currency === "JPY" ? 0 : 2)}`;
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
