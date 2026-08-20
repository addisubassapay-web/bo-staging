// ISO 3166-1 alpha-2 → { name, flag } for common storefront countries.
// The flag is rendered via regional-indicator unicode which combines to the
// national flag glyph on every modern OS + browser (mobile & desktop).
export const COUNTRIES = [
  { code: "US", name: "United States" },
  { code: "CA", name: "Canada" },
  { code: "MX", name: "Mexico" },
  { code: "BR", name: "Brazil" },
  { code: "AR", name: "Argentina" },
  { code: "GB", name: "United Kingdom" },
  { code: "IE", name: "Ireland" },
  { code: "FR", name: "France" },
  { code: "DE", name: "Germany" },
  { code: "ES", name: "Spain" },
  { code: "IT", name: "Italy" },
  { code: "PT", name: "Portugal" },
  { code: "NL", name: "Netherlands" },
  { code: "BE", name: "Belgium" },
  { code: "CH", name: "Switzerland" },
  { code: "SE", name: "Sweden" },
  { code: "NO", name: "Norway" },
  { code: "DK", name: "Denmark" },
  { code: "FI", name: "Finland" },
  { code: "PL", name: "Poland" },
  { code: "CZ", name: "Czechia" },
  { code: "GR", name: "Greece" },
  { code: "TR", name: "Türkiye" },
  { code: "RU", name: "Russia" },
  { code: "UA", name: "Ukraine" },
  { code: "IN", name: "India" },
  { code: "PK", name: "Pakistan" },
  { code: "BD", name: "Bangladesh" },
  { code: "CN", name: "China" },
  { code: "JP", name: "Japan" },
  { code: "KR", name: "South Korea" },
  { code: "SG", name: "Singapore" },
  { code: "MY", name: "Malaysia" },
  { code: "TH", name: "Thailand" },
  { code: "VN", name: "Vietnam" },
  { code: "PH", name: "Philippines" },
  { code: "ID", name: "Indonesia" },
  { code: "AU", name: "Australia" },
  { code: "NZ", name: "New Zealand" },
  { code: "AE", name: "United Arab Emirates" },
  { code: "SA", name: "Saudi Arabia" },
  { code: "IL", name: "Israel" },
  { code: "EG", name: "Egypt" },
  { code: "NG", name: "Nigeria" },
  { code: "GH", name: "Ghana" },
  { code: "KE", name: "Kenya" },
  { code: "ZA", name: "South Africa" },
  { code: "MA", name: "Morocco" },
  { code: "DZ", name: "Algeria" },
  { code: "ET", name: "Ethiopia" },
  { code: "CI", name: "Côte d’Ivoire" },
  { code: "SN", name: "Senegal" },
  { code: "CM", name: "Cameroon" },
  { code: "CO", name: "Colombia" },
  { code: "CL", name: "Chile" },
  { code: "PE", name: "Peru" },
  { code: "VE", name: "Venezuela" },
];

/** Return the emoji flag for a 2-letter ISO country code (case-insensitive). */
export function flagEmoji(code) {
  if (!code || typeof code !== "string" || code.length !== 2) return "";
  const cc = code.toUpperCase();
  const A = 0x41;
  const base = 0x1f1e6;
  const c0 = cc.charCodeAt(0);
  const c1 = cc.charCodeAt(1);
  if (c0 < A || c0 > A + 25 || c1 < A || c1 > A + 25) return "";
  return String.fromCodePoint(base + (c0 - A)) + String.fromCodePoint(base + (c1 - A));
}

export function countryName(code) {
  if (!code) return "";
  const found = COUNTRIES.find((c) => c.code === code.toUpperCase());
  return found ? found.name : code.toUpperCase();
}
