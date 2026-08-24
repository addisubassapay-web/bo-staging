import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLang } from "@/context/LanguageContext";
import {
  Menu as MenuIcon, X, Package, Search, ShoppingCart, Heart, MessageSquare, Wallet,
  AlertCircle, Store, BarChart3, Users, Link as LinkIcon, ShieldCheck, Settings, User,
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
    <span className="h-8 w-8 rounded-lg bg-[#FF7A18]/10 text-[#FF7A18] grid place-items-center shrink-0">
      <Icon className="h-4 w-4" />
    </span>
    <span className="text-sm font-medium">{children}</span>
  </Link>
);

const GlobalNavMenu = () => {
  const { user } = useAuth();
  const { t } = useLang();
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
        className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] grid place-items-center transition text-neutral-700 dark:text-neutral-200 shrink-0"
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
            <img src="/logo-mark.png" alt="Mercari-Global" className="h-9 w-9 shrink-0" />
            <div className="leading-tight">
              <div className="text-base font-bold text-neutral-900 dark:text-neutral-100">Mercari-Global <span className="text-[#FF7A18]">Global</span></div>
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
