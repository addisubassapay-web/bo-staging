import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("mercari_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default api;

// --- Currency-aware price formatter (used by non-context call sites) ---
// Fallback rates match CurrencyContext.FALLBACK_RATES. Live rates fetched
// by CurrencyContext are cached to `mercari_rates` in localStorage and
// win over these static values.
const STATIC_RATES = {
  USD: 1, EUR: 0.92, GBP: 0.78, JPY: 155, INR: 83.2, CAD: 1.36,
  AUD: 1.52, BRL: 5.05, MXN: 17.1, CNY: 7.18, KRW: 1345, SGD: 1.34, AED: 3.673,
};
const CURRENCY_LOCALES = {
  USD: "en-US", EUR: "de-DE", GBP: "en-GB", JPY: "ja-JP", INR: "en-IN", CAD: "en-CA",
  AUD: "en-AU", BRL: "pt-BR", MXN: "es-MX", CNY: "zh-CN", KRW: "ko-KR", SGD: "en-SG", AED: "ar-AE",
};

const readLiveRate = (currency) => {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem("mercari_rates");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const rate = parsed?.rates?.[currency];
    return typeof rate === "number" ? rate : null;
  } catch { return null; }
};

export const formatPrice = (usd) => {
  const currency = (typeof localStorage !== "undefined" && localStorage.getItem("mercari_currency")) || "USD";
  const rate = readLiveRate(currency) ?? STATIC_RATES[currency] ?? 1;
  const value = Number(usd || 0) * rate;
  const locale = CURRENCY_LOCALES[currency] || "en-US";
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      maximumFractionDigits: currency === "JPY" || currency === "KRW" ? 0 : 2,
    }).format(value);
  } catch {
    return `$${value.toFixed(2)}`;
  }
};

export const conditionLabel = (c) => {
  const map = { new: "New", like_new: "Like new", good: "Good", fair: "Fair", poor: "Poor" };
  return map[c] || c;
};
