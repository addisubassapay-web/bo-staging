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
const STATIC_RATES = { USD: 1, EUR: 0.92, GBP: 0.78, JPY: 155, INR: 83.2, CAD: 1.36 };
const CURRENCY_LOCALES = {
  USD: "en-US", EUR: "de-DE", GBP: "en-GB", JPY: "ja-JP", INR: "en-IN", CAD: "en-CA",
};

export const formatPrice = (usd) => {
  const currency = (typeof localStorage !== "undefined" && localStorage.getItem("mercari_currency")) || "USD";
  const rate = STATIC_RATES[currency] ?? 1;
  const value = Number(usd || 0) * rate;
  const locale = CURRENCY_LOCALES[currency] || "en-US";
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      maximumFractionDigits: currency === "JPY" ? 0 : 2,
    }).format(value);
  } catch {
    return `$${value.toFixed(2)}`;
  }
};

export const conditionLabel = (c) => {
  const map = { new: "New", like_new: "Like new", good: "Good", fair: "Fair", poor: "Poor" };
  return map[c] || c;
};
