/**
 * Geo auto-detect — best-effort language + currency detection from
 * navigator.language on the very first visit. Users can override at any
 * time via the pickers; overrides are persisted to localStorage and win
 * over any auto-detect on subsequent visits.
 */

// Map browser locale primary tag → app language code.
const LANG_MAP = {
  en: "en", es: "es", fr: "fr", de: "de", it: "it", pt: "pt",
  ja: "ja", zh: "zh", ar: "ar", hi: "hi",
};

// Map region code (uppercase) → currency code.
const REGION_CURRENCY = {
  US: "USD", CA: "CAD", GB: "GBP", IE: "EUR",
  DE: "EUR", FR: "EUR", ES: "EUR", IT: "EUR", NL: "EUR", PT: "EUR", AT: "EUR", BE: "EUR", GR: "EUR", FI: "EUR",
  JP: "JPY", IN: "INR", AU: "AUD", NZ: "AUD",
  BR: "BRL", MX: "MXN", CN: "CNY", HK: "CNY", TW: "CNY",
  KR: "KRW", SG: "SGD", MY: "SGD",
  AE: "AED", SA: "AED", QA: "AED", KW: "AED", OM: "AED", BH: "AED",
};

// Currencies the app supports — output must match CURRENCY_META keys.
const SUPPORTED_CURRENCIES = new Set([
  "USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD", "BRL",
  "MXN", "CNY", "KRW", "SGD", "AED",
]);

const SUPPORTED_LANGS = new Set(Object.keys(LANG_MAP));

/**
 * Read navigator.language → return { lang, currency } (either may be null).
 */
export const detectGeo = () => {
  if (typeof navigator === "undefined") return { lang: null, currency: null };
  // navigator.languages is an array in preference order; fall back to .language
  const list = Array.isArray(navigator.languages) && navigator.languages.length
    ? navigator.languages
    : [navigator.language || "en-US"];

  let lang = null;
  let currency = null;

  for (const raw of list) {
    if (!raw) continue;
    const [primary, region] = raw.split(/[-_]/);
    if (!lang && primary && SUPPORTED_LANGS.has(primary.toLowerCase())) {
      lang = LANG_MAP[primary.toLowerCase()];
    }
    if (!currency && region) {
      const guess = REGION_CURRENCY[region.toUpperCase()];
      if (guess && SUPPORTED_CURRENCIES.has(guess)) currency = guess;
    }
    if (lang && currency) break;
  }
  return { lang, currency };
};

/**
 * Choose the initial value for a context: an existing localStorage
 * override always wins; otherwise use the geo-detected value; otherwise
 * fall back to the given default. Also marks localStorage that geo
 * auto-detect has happened once so future overrides stick.
 */
export const chooseInitial = (storageKey, fallback, geoValue) => {
  if (typeof window === "undefined") return fallback;
  try {
    const existing = localStorage.getItem(storageKey);
    if (existing) return existing;
    if (geoValue) {
      // Persist the auto-detected choice so subsequent visits are stable
      localStorage.setItem(storageKey, geoValue);
      return geoValue;
    }
  } catch { /* ignore storage errors */ }
  return fallback;
};
