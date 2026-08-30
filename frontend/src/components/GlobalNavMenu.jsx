import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLang, LANGUAGES } from "@/context/LanguageContext";
import { useCurrency, CURRENCY_LIST } from "@/context/CurrencyContext";
import {
  Menu as MenuIcon, X, Package, Search, ShoppingCart, Heart, MessageSquare, Wallet,
  AlertCircle, Store, BarChart3, Users, Link as LinkIcon, ShieldCheck, Settings, User,
  Globe, DollarSign,
} from "lucide-react";

/**
 * GlobalNavMenu — persistent 3-stroke button at the top-left of every page.
 * Opens a slide-out panel with links to the main platform pages.
 */
const NavItem = ({ to, icon: Icon, children, onClose, testid }) => (
  <Link
    to={to}
    onClick={onClose}
    className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-neutral-800 dark:text-neutral-100 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition"
    data-testid={testid}
  >
    <span className="h-8 w-8 rounded-lg bg-[#1E40AF]/10 text-[#1E40AF] grid place-items-center shrink-0">
      <Icon className="h-4 w-4" />
    </span>
    <span className="text-sm font-medium">{children}</span>
  </Link>
);

const GlobalNavMenu = () => {
  const { user } = useAuth();
  const { t, lang, setLang } = useLang();
  const { currency, setCurrency, meta } = useCurrency();
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setOpen(true)}
        aria-label="Open main menu"
        className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#1E40AF] grid place-items-center transition text-neutral-700 dark:text-neutral-200 shrink-0"
        data-testid="global-nav-btn"
      >
        <MenuIcon className="h-5 w-5" />
      </button>

      {/* Backdrop + panel */}
      <div
        onClick={close}
        className={`fixed inset-0 z-50 bg-black/50 backdrop-blur-sm transition-opacity ${open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
        data-testid="global-nav-backdrop"
      />
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-[86%] max-w-sm bg-white dark:bg-neutral-950 shadow-2xl transform transition-transform duration-300 flex flex-col ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-hidden={!open}
        data-testid="global-nav-panel"
      >
        <div className="flex items-center justify-between px-4 h-16 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
          <div className="flex items-center gap-2">
            <img src="/logo-mark.png" alt="BlueOcean" className="h-9 w-9 shrink-0" />
            <div className="leading-tight">
              <div className="text-base font-bold text-neutral-900 dark:text-neutral-100">BlueOcean</div>
              <div className="text-[10px] text-neutral-500 dark:text-neutral-400 -mt-0.5">{t("menu.mainPages")}</div>
            </div>
          </div>
          <button
            onClick={close}
            aria-label="Close menu"
            className="h-10 w-10 rounded-full grid place-items-center text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            data-testid="global-nav-close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {/* Language + Currency — quick switchers at the top of the drawer.
              Values persist to localStorage via the context providers. */}
          <div className="px-2 pt-2 pb-3 space-y-2" data-testid="gnav-prefs">
            <label className="flex items-center gap-3 rounded-xl bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 px-3 py-2">
              <span className="h-8 w-8 rounded-lg bg-sky-100 text-sky-700 grid place-items-center shrink-0">
                <Globe className="h-4 w-4" />
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Language</div>
                <select
                  value={lang}
                  onChange={(e) => setLang(e.target.value)}
                  className="mt-0.5 w-full bg-transparent text-sm font-semibold text-neutral-900 dark:text-neutral-100 focus:outline-none cursor-pointer"
                  data-testid="gnav-lang-select"
                  aria-label="Choose language"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>{l.flag} {l.label}</option>
                  ))}
                </select>
              </div>
            </label>
            <label className="flex items-center gap-3 rounded-xl bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 px-3 py-2">
              <span className="h-8 w-8 rounded-lg bg-emerald-100 text-emerald-700 grid place-items-center shrink-0">
                <DollarSign className="h-4 w-4" />
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Currency</div>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="mt-0.5 w-full bg-transparent text-sm font-semibold text-neutral-900 dark:text-neutral-100 focus:outline-none cursor-pointer"
                  data-testid="gnav-currency-select"
                  aria-label="Choose currency"
                >
                  {CURRENCY_LIST.map((c) => (
                    <option key={c} value={c}>
                      {c} {meta?.symbol && c === currency ? `(${meta.symbol})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            </label>
          </div>

          <div className="h-px bg-neutral-200 dark:bg-neutral-800 mx-2" />

          <NavItem to="/" icon={Package} onClose={close} testid="gnav-home">{t("menu.home")}</NavItem>
          <NavItem to="/search" icon={Search} onClose={close} testid="gnav-search">{t("menu.browse")}</NavItem>
          <NavItem to="/cart" icon={ShoppingCart} onClose={close} testid="gnav-cart">{t("cart.viewCart")}</NavItem>
          <NavItem to="/favorites" icon={Heart} onClose={close} testid="gnav-favorites">{t("menu.favorites")}</NavItem>
          {user ? (
            <>
              <div className="my-2 px-4 text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold">Your account</div>
              <NavItem to="/sell" icon={Package} onClose={close} testid="gnav-sell">{t("nav.sell")}</NavItem>
              <NavItem to="/chat" icon={MessageSquare} onClose={close} testid="gnav-chat">{t("menu.messages")}</NavItem>
              <NavItem to="/wallet" icon={Wallet} onClose={close} testid="gnav-wallet">{t("menu.wallet")}</NavItem>
              <NavItem to="/disputes" icon={AlertCircle} onClose={close} testid="gnav-disputes">{t("menu.disputes")}</NavItem>
              <NavItem to="/my/store" icon={Store} onClose={close} testid="gnav-store">{t("menu.myStore")}</NavItem>
              <NavItem to="/store/analytics" icon={BarChart3} onClose={close} testid="gnav-analytics">{t("menu.storeAnalytics")}</NavItem>
              <NavItem to="/referrals" icon={Users} onClose={close} testid="gnav-referrals">{t("menu.referrals")}</NavItem>
              <NavItem to="/affiliate" icon={LinkIcon} onClose={close} testid="gnav-affiliate">{t("menu.affiliate")}</NavItem>
              <NavItem to="/verify" icon={ShieldCheck} onClose={close} testid="gnav-verify">Verification</NavItem>
              <NavItem to="/profile" icon={User} onClose={close} testid="gnav-profile">{t("menu.profile")}</NavItem>
              {user.role === "admin" && (
                <NavItem to="/admin" icon={Settings} onClose={close} testid="gnav-admin">{t("menu.admin")}</NavItem>
              )}
            </>
          ) : (
            <>
              <NavItem to="/login" icon={User} onClose={close} testid="gnav-login">{t("nav.login")}</NavItem>
              <NavItem to="/register" icon={User} onClose={close} testid="gnav-register">{t("nav.register")}</NavItem>
            </>
          )}
        </nav>
      </aside>
    </>
  );
};

export default GlobalNavMenu;
