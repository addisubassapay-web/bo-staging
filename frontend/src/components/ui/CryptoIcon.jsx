import React from "react";

/**
 * CryptoIcon — inline SVG brand marks for popular cryptocurrencies.
 * Every coin is rendered as a real logo (not a generic circle-with-letter)
 * on top of its brand colour disc. Falls back to a gradient chip with the
 * ticker for unknown symbols so the UI never breaks.
 *
 * Props:
 *  - symbol: string — coin ticker, e.g. "BTC", "ETH", "USDT", "SOL"
 *  - size: number (px, default 28)
 *  - className / "data-testid": passthrough
 *  - showTicker: boolean — render "SYMBOL" text next to the mark
 *  - flat: boolean — omit the coloured disc (icon only, uses currentColor)
 */
const COIN_MAP = {
  BTC: {
    name: "Bitcoin", bg: "#F7931A", ink: "#FFFFFF",
    // Simplified ₿ glyph
    path: <path d="M20.3 13.5c.5-2-1-3-3.1-3.7l.6-2.4-1.5-.4-.6 2.4c-.4-.1-.8-.2-1.2-.3l.6-2.4-1.5-.4-.6 2.4-3-.7-.4 1.6s1.1.2 1.1.3c.6.2.7.6.7.9L10.7 15c0 .1-.1.4-.4.4h-1L9 17.3l2.9.7-.6 2.4 1.5.4.6-2.4 1.2.3-.6 2.4 1.5.4.6-2.4c2.6.5 4.5.3 5.3-2 .7-1.9 0-3-1.4-3.7 1-.3 1.8-.9 2-2.5zm-3.6 4.8c-.5 1.9-3.6.9-4.6.6l.8-3.2c1 .3 4.2.7 3.8 2.6zm.5-4.9c-.4 1.7-3 .9-3.8.7l.7-2.9c.9.2 3.6.6 3.1 2.2z" />
  },
  ETH: {
    name: "Ethereum", bg: "#627EEA", ink: "#FFFFFF",
    path: <><path d="M16 4v9l7 3.1z" fillOpacity="0.8" /><path d="M16 4L9 16.1l7-3.1z" /><path d="M16 22.7v5.3l7-9.7z" fillOpacity="0.8" /><path d="M16 28v-5.3l-7-4.4z" /><path d="M16 21.4l7-4.4-7-3.1z" fillOpacity="0.5" /><path d="M9 17l7 4.4v-7.5z" fillOpacity="0.9" /></>
  },
  USDT: {
    name: "Tether", bg: "#26A17B", ink: "#FFFFFF",
    // Simple "T" wordmark
    path: <path d="M17.9 15.6v-2.3H23V9.8H9v3.5h5.1v2.3c-4 .2-7 1-7 1.9 0 .9 3 1.7 7 1.9v7.3h3.8v-7.3c4-.2 7-1 7-1.9 0-.9-3-1.7-7-1.9zm0 3.2v-.01c-.1 0-.6 0-1.9 0-1 0-1.6 0-1.9 0v.01c-3.3-.1-5.7-.7-5.7-1.4 0-.7 2.5-1.3 5.7-1.4v2.3c.2 0 .9.1 1.9.1 1.4 0 1.8 0 1.9-.1v-2.3c3.3.1 5.7.7 5.7 1.4 0 .7-2.5 1.3-5.7 1.4z" />
  },
  USDC: {
    name: "USD Coin", bg: "#2775CA", ink: "#FFFFFF",
    path: <><circle cx="16" cy="16" r="12" fill="none" stroke="#FFFFFF" strokeWidth="1.6" /><text x="16" y="20.5" fontSize="12" fontWeight="800" fontFamily="system-ui" textAnchor="middle" fill="#FFFFFF">$</text><path d="M11 12a4 4 0 018 0M11 20a4 4 0 008 0" fill="none" stroke="#FFFFFF" strokeWidth="1.4" strokeLinecap="round" opacity="0.35" /></>
  },
  BNB: {
    name: "BNB", bg: "#F0B90B", ink: "#FFFFFF",
    path: <><path d="M16 8l3 3-3 3-3-3zM11 13l3 3-3 3-3-3zM21 13l3 3-3 3-3-3zM16 18l3 3-3 3-3-3z" /></>
  },
  SOL: {
    name: "Solana", bg: "linear-gradient(135deg,#9945FF 0%,#14F195 100%)", ink: "#FFFFFF",
    path: <><path d="M8 21.5l2-2h14l-2 2H8zM8 15l2-2h14l-2 2H8zM8 8.5l2-2h14l-2 2H8z" /></>
  },
  XRP: {
    name: "XRP", bg: "#111111", ink: "#FFFFFF",
    path: <path d="M22.5 8L16 13.4 9.5 8H6l7.5 7L6 24h3.5l6.5-5.5L22.5 24H26l-7.5-9L26 8h-3.5z" />
  },
  TRX: {
    name: "TRON", bg: "#FF060A", ink: "#FFFFFF",
    path: <path d="M6 8l12 3 8 3-16 12z M8 10l14 3.4L11.5 22 8 10z" fillRule="evenodd" />
  },
  MATIC: {
    name: "Polygon", bg: "#8247E5", ink: "#FFFFFF",
    path: <path d="M20.5 12.2l-3.5-2c-.3-.2-.7-.2-1 0l-3.5 2c-.3.2-.5.5-.5.9v4c0 .4.2.7.5.9l3.5 2c.3.2.7.2 1 0l3.5-2c.3-.2.5-.5.5-.9v-4c0-.4-.2-.7-.5-.9zM11 16v3l-2 1.2c-.3.2-.7.2-1 0l-3.5-2C4.2 18 4 17.7 4 17.3v-4c0-.4.2-.7.5-.9l3.5-2c.3-.2.7-.2 1 0L11 11.7c-.3.2-.5.5-.5.9v.9l-1.5.9L7 13l-2 1.2v2.6L7 18l2-1.2v-1z" opacity="0.9" />
  },
  POL: { alias: "MATIC" },
  LTC: {
    name: "Litecoin", bg: "#345D9D", ink: "#FFFFFF",
    path: <path d="M14 6l-2 8-2 .8-.5 2 2-.8L10 22h12l1-3.5h-8l.8-3.3 2-.8.5-2-2 .8L18 6h-4z" />
  },
  DOGE: {
    name: "Dogecoin", bg: "#C2A633", ink: "#FFFFFF",
    path: <path d="M11 8h6c3.3 0 6 3.6 6 8s-2.7 8-6 8h-6v-6h-2v-4h2V8zm3 4v8h3c1.7 0 3-1.8 3-4s-1.3-4-3-4h-3z" />
  },
  ADA: {
    name: "Cardano", bg: "#0033AD", ink: "#FFFFFF",
    path: <><circle cx="16" cy="16" r="1.6" /><circle cx="16" cy="9" r="1.1" /><circle cx="16" cy="23" r="1.1" /><circle cx="9.5" cy="12.5" r="1.1" /><circle cx="22.5" cy="12.5" r="1.1" /><circle cx="9.5" cy="19.5" r="1.1" /><circle cx="22.5" cy="19.5" r="1.1" /><circle cx="8" cy="16" r="0.9" /><circle cx="24" cy="16" r="0.9" /></>
  },
  DOT: {
    name: "Polkadot", bg: "#E6007A", ink: "#FFFFFF",
    path: <><ellipse cx="16" cy="8" rx="3" ry="2" /><ellipse cx="16" cy="24" rx="3" ry="2" /><ellipse cx="10" cy="12" rx="2" ry="3" transform="rotate(-30 10 12)" /><ellipse cx="22" cy="20" rx="2" ry="3" transform="rotate(-30 22 20)" /><ellipse cx="10" cy="20" rx="2" ry="3" transform="rotate(30 10 20)" /><ellipse cx="22" cy="12" rx="2" ry="3" transform="rotate(30 22 12)" /></>
  },
  AVAX: {
    name: "Avalanche", bg: "#E84142", ink: "#FFFFFF",
    path: <path d="M16 6l10 18H20l-2-4h-8l6-14zm-5 14l-3 4H4l4-8 3 4z" />
  },
  LINK: {
    name: "Chainlink", bg: "#2A5ADA", ink: "#FFFFFF",
    path: <path d="M16 6L6 12v8l10 6 10-6v-8L16 6zm0 3.5l7 4v5L16 22.5 9 18.5v-5l7-4z" />
  },
  ATOM: {
    name: "Cosmos", bg: "#2E3148", ink: "#FFFFFF",
    path: <><circle cx="16" cy="16" r="1.6" /><ellipse cx="16" cy="16" rx="10" ry="4" fill="none" stroke="#FFFFFF" strokeWidth="1.4" /><ellipse cx="16" cy="16" rx="10" ry="4" fill="none" stroke="#FFFFFF" strokeWidth="1.4" transform="rotate(60 16 16)" /><ellipse cx="16" cy="16" rx="10" ry="4" fill="none" stroke="#FFFFFF" strokeWidth="1.4" transform="rotate(120 16 16)" /></>
  },
  XLM: {
    name: "Stellar", bg: "#000000", ink: "#FFFFFF",
    path: <path d="M6 10l20 4-20 4v-8zm12 4L6 16l6 1 6-3z" opacity="0.9" />
  },
  BCH: {
    name: "Bitcoin Cash", bg: "#0AC18E", ink: "#FFFFFF",
    path: <path d="M17.9 15.6v-2.3H23V9.8H9v3.5h5.1v2.3c-4 .2-7 1-7 1.9 0 .9 3 1.7 7 1.9v7.3h3.8v-7.3c4-.2 7-1 7-1.9 0-.9-3-1.7-7-1.9z" />
  },
  DAI: {
    name: "Dai", bg: "#F5AC37", ink: "#FFFFFF",
    path: <path d="M9 10h6.5c3.6 0 6.5 2.7 6.5 6s-2.9 6-6.5 6H9v-3H7v-2h2v-2H7v-2h2v-3zm3 3v9h3.5c2 0 3.5-2 3.5-4.5S17.5 13 15.5 13H12z" />
  },
  TON: {
    name: "Toncoin", bg: "#0098EA", ink: "#FFFFFF",
    path: <path d="M8 10h16l-8 14L8 10zm2.7 1.5l5.3 9.2 5.3-9.2h-10.6z" />
  },
};

/* Resolve alias entries once at module load */
Object.keys(COIN_MAP).forEach((k) => {
  const cfg = COIN_MAP[k];
  if (cfg && cfg.alias) COIN_MAP[k] = COIN_MAP[cfg.alias];
});

export const CryptoIcon = ({
  symbol = "BTC",
  size = 28,
  flat = false,
  showTicker = false,
  className = "",
  "data-testid": testId,
}) => {
  const key = String(symbol || "").toUpperCase();
  const cfg = COIN_MAP[key];
  const uid = React.useId();

  // Fallback: gradient chip with the ticker for unknown coins.
  if (!cfg) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 ${className}`}
        data-testid={testId || `crypto-icon-${key}`}
      >
        <span
          className="inline-grid place-items-center rounded-full font-extrabold text-white shadow-sm ring-1 ring-black/5"
          style={{
            width: size, height: size,
            fontSize: size * 0.36,
            background: "linear-gradient(135deg,#5459E8,#818CF8)",
          }}
          aria-label={key}
        >
          {key.slice(0, 3)}
        </span>
        {showTicker && <span className="font-semibold text-sm">{key}</span>}
      </span>
    );
  }

  const gradId = `coin-grad-${uid}`;
  const bgIsGradient = typeof cfg.bg === "string" && cfg.bg.startsWith("linear-gradient");
  const svgBg = flat ? "none" : (bgIsGradient ? `url(#${gradId})` : cfg.bg);

  return (
    <span
      className={`inline-flex items-center gap-1.5 ${className}`}
      data-testid={testId || `crypto-icon-${key}`}
      title={cfg.name}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 32 32"
        width={size}
        height={size}
        role="img"
        aria-label={cfg.name}
        className="shrink-0 drop-shadow-sm"
      >
        {bgIsGradient && !flat && (
          <defs>
            <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
              {/* Two-stop parse: #9945FF 0%, #14F195 100% */}
              {cfg.bg.replace("linear-gradient(135deg,", "").replace(")", "").split(",").map((seg, i) => {
                const [color, stop] = seg.trim().split(/\s+/);
                return <stop key={i} offset={stop || `${i * 100}%`} stopColor={color} />;
              })}
            </linearGradient>
          </defs>
        )}
        {!flat && <circle cx="16" cy="16" r="16" fill={svgBg} />}
        <g fill={flat ? "currentColor" : cfg.ink} stroke="none">
          {cfg.path}
        </g>
      </svg>
      {showTicker && <span className="font-semibold text-sm text-neutral-800 dark:text-neutral-100">{key}</span>}
    </span>
  );
};

/** Named export for the list of coins that ship with a real icon */
export const SUPPORTED_CRYPTOS = Object.keys(COIN_MAP);

export default CryptoIcon;
