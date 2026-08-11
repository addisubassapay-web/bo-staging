import React, { createContext, useContext, useState, useCallback, useMemo } from "react";

const LanguageContext = createContext(null);

/**
 * Minimal i18n. Covers the most-visible header + nav + product-card strings.
 * Falls back to English for any missing key. Full app localization is a follow-up.
 */
const DICT = {
  en: {
    "nav.categories": "Categories",
    "nav.sell": "Sell",
    "nav.signIn": "Sign in",
    "nav.help": "Help",
    "nav.login": "Login",
    "nav.register": "Register",
    "search.placeholder": "Search for anything you love…",
    "search.recentTitle": "Recent searches",
    "search.trendingTitle": "Trending now",
    "search.suggestions": "Suggestions",
    "search.brands": "Brands",
    "search.seeAll": "See all results for",
    "search.vibeToggle": "Try Vibe search",
    "search.vibeOn": "Vibe search on",
    "cta.shopNow": "Shop Now",
    "cta.browse": "Browse everything",
    "cart.title": "Your cart",
    "cart.empty": "Your cart is empty",
    "cart.subtotal": "Subtotal",
    "cart.checkout": "Checkout",
    "cart.viewCart": "View cart",
    "topstrip.marketplace": "Mercari Global Marketplace",
    "topstrip.returns": "Free returns on eligible items",
    "topstrip.deals": "Daily Flash Deals",
    "menu.mainPages": "Main pages",
    "menu.home": "Home",
    "menu.browse": "Browse",
    "menu.favorites": "Favorites",
    "menu.messages": "Messages",
    "menu.wallet": "Wallet",
    "menu.disputes": "Disputes",
    "menu.myStore": "My store",
    "menu.storeAnalytics": "Store analytics",
    "menu.referrals": "Referrals",
    "menu.affiliate": "Affiliate",
    "menu.profile": "Profile",
    "menu.admin": "Admin panel",
    "commandPalette.title": "Search everywhere",
    "commandPalette.placeholder": "Search products, pages, or type / for commands",
    "commandPalette.hint": "Press ⌘K to open anywhere",
  },
  es: {
    "nav.categories": "Categorías",
    "nav.sell": "Vender",
    "nav.signIn": "Ingresar",
    "nav.help": "Ayuda",
    "nav.login": "Iniciar sesión",
    "nav.register": "Registrarse",
    "search.placeholder": "Busca cualquier cosa que ames…",
    "search.recentTitle": "Búsquedas recientes",
    "search.trendingTitle": "Tendencia ahora",
    "search.suggestions": "Sugerencias",
    "search.brands": "Marcas",
    "search.seeAll": "Ver todos los resultados de",
    "search.vibeToggle": "Buscar por vibra",
    "search.vibeOn": "Búsqueda por vibra activa",
    "cta.shopNow": "Comprar ahora",
    "cta.browse": "Explorar todo",
    "cart.title": "Tu carrito",
    "cart.empty": "Tu carrito está vacío",
    "cart.subtotal": "Subtotal",
    "cart.checkout": "Pagar",
    "cart.viewCart": "Ver carrito",
    "topstrip.marketplace": "Mercado Global Mercari",
    "topstrip.returns": "Devoluciones gratis en productos elegibles",
    "topstrip.deals": "Ofertas Flash diarias",
    "menu.mainPages": "Páginas principales",
    "menu.home": "Inicio",
    "menu.browse": "Explorar",
    "menu.favorites": "Favoritos",
    "menu.messages": "Mensajes",
    "menu.wallet": "Cartera",
    "menu.disputes": "Disputas",
    "menu.myStore": "Mi tienda",
    "menu.storeAnalytics": "Analíticas",
    "menu.referrals": "Referidos",
    "menu.affiliate": "Afiliados",
    "menu.profile": "Perfil",
    "menu.admin": "Panel admin",
    "commandPalette.title": "Buscar en todo",
    "commandPalette.placeholder": "Busca productos, páginas o escribe / para comandos",
    "commandPalette.hint": "Presiona ⌘K en cualquier lugar",
  },
  fr: {
    "nav.categories": "Catégories",
    "nav.sell": "Vendre",
    "nav.signIn": "Connexion",
    "nav.help": "Aide",
    "nav.login": "Connexion",
    "nav.register": "Inscription",
    "search.placeholder": "Cherchez tout ce que vous aimez…",
    "search.recentTitle": "Recherches récentes",
    "search.trendingTitle": "Tendance",
    "search.suggestions": "Suggestions",
    "search.brands": "Marques",
    "search.seeAll": "Voir tous les résultats pour",
    "search.vibeToggle": "Essayer la recherche par vibe",
    "search.vibeOn": "Recherche par vibe activée",
    "cta.shopNow": "Acheter maintenant",
    "cta.browse": "Tout parcourir",
    "cart.title": "Votre panier",
    "cart.empty": "Votre panier est vide",
    "cart.subtotal": "Sous-total",
    "cart.checkout": "Commander",
    "cart.viewCart": "Voir le panier",
    "topstrip.marketplace": "Marché Global Mercari",
    "topstrip.returns": "Retours gratuits sur articles éligibles",
    "topstrip.deals": "Offres Flash quotidiennes",
    "menu.mainPages": "Pages principales",
    "menu.home": "Accueil",
    "menu.browse": "Parcourir",
    "menu.favorites": "Favoris",
    "menu.messages": "Messages",
    "menu.wallet": "Portefeuille",
    "menu.disputes": "Litiges",
    "menu.myStore": "Ma boutique",
    "menu.storeAnalytics": "Analyses",
    "menu.referrals": "Parrainage",
    "menu.affiliate": "Affilié",
    "menu.profile": "Profil",
    "menu.admin": "Admin",
    "commandPalette.title": "Rechercher partout",
    "commandPalette.placeholder": "Produits, pages, ou tapez / pour commandes",
    "commandPalette.hint": "Appuyez sur ⌘K partout",
  },
  ja: {
    "nav.categories": "カテゴリ",
    "nav.sell": "出品",
    "nav.signIn": "サインイン",
    "nav.help": "ヘルプ",
    "nav.login": "ログイン",
    "nav.register": "登録",
    "search.placeholder": "何でも検索…",
    "search.recentTitle": "最近の検索",
    "search.trendingTitle": "トレンド",
    "search.suggestions": "候補",
    "search.brands": "ブランド",
    "search.seeAll": "すべての結果を見る",
    "search.vibeToggle": "ヴァイブ検索を試す",
    "search.vibeOn": "ヴァイブ検索ON",
    "cta.shopNow": "今すぐ購入",
    "cta.browse": "すべて見る",
    "cart.title": "カート",
    "cart.empty": "カートは空です",
    "cart.subtotal": "小計",
    "cart.checkout": "購入手続き",
    "cart.viewCart": "カートを見る",
    "topstrip.marketplace": "メルカリ グローバル",
    "topstrip.returns": "対象商品は返品無料",
    "topstrip.deals": "毎日フラッシュセール",
    "menu.mainPages": "メインページ",
    "menu.home": "ホーム",
    "menu.browse": "探す",
    "menu.favorites": "お気に入り",
    "menu.messages": "メッセージ",
    "menu.wallet": "ウォレット",
    "menu.disputes": "トラブル",
    "menu.myStore": "マイストア",
    "menu.storeAnalytics": "分析",
    "menu.referrals": "紹介",
    "menu.affiliate": "アフィリエイト",
    "menu.profile": "プロフィール",
    "menu.admin": "管理者",
    "commandPalette.title": "全体を検索",
    "commandPalette.placeholder": "商品、ページ、または / でコマンド",
    "commandPalette.hint": "どこでも ⌘K で開く",
  },
};

export const LANGUAGES = [
  { code: "en", label: "English", flag: "🇺🇸" },
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "ja", label: "日本語", flag: "🇯🇵" },
];

export const LanguageProvider = ({ children }) => {
  const [lang, setLangState] = useState(() => localStorage.getItem("mercari_lang") || "en");

  const setLang = useCallback((l) => {
    setLangState(l);
    localStorage.setItem("mercari_lang", l);
    try { document.documentElement.setAttribute("lang", l); } catch { /* ignore */ }
  }, []);

  const t = useCallback(
    (key, fallback) => {
      const bucket = DICT[lang] || DICT.en;
      return bucket[key] || DICT.en[key] || fallback || key;
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};

export const useLang = () => {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used within LanguageProvider");
  return ctx;
};
