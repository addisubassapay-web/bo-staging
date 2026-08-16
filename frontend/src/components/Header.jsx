import React, { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  ShoppingCart, User, LogOut, Package, Settings, Store, Wallet, Link as LinkIcon,
  Users, MessageSquare, BarChart3, ShieldCheck, Heart, Sun, Moon, AlertCircle, Command, ShoppingBag,
} from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { useLang } from "@/context/LanguageContext";
import api from "@/lib/api";
import NotificationsBell from "@/components/NotificationsBell";
import LiveSyncBadge from "@/components/LiveSyncBadge";
import SearchAutocomplete from "@/components/SearchAutocomplete";
import CategoryMegaMenu from "@/components/CategoryMegaMenu";
import CurrencyPicker from "@/components/CurrencyPicker";
import LanguagePicker from "@/components/LanguagePicker";
import MiniCart from "@/components/MiniCart";
import GlobalNavMenu from "@/components/GlobalNavMenu";
import CommandPalette, { useCommandPaletteShortcut } from "@/components/CommandPalette";
import BrandMark from "@/components/BrandMark";

const TopStrip = ({ user, onLogout }) => {
  const { t } = useLang();
  return (
    <div className="bg-[#0F1113] text-neutral-200 text-xs dark:bg-black dark:text-neutral-300">
      <div className="max-w-7xl mx-auto px-4 h-8 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 overflow-x-auto whitespace-nowrap min-w-0">
          <span className="flex items-center gap-1.5"><span className="text-cyan-400">◈</span>{t("topstrip.marketplace")}</span>
          <span className="hidden sm:flex items-center gap-1.5"><span className="text-emerald-400">◆</span>{t("topstrip.returns")}</span>
          <span className="hidden md:flex items-center gap-1.5"><span className="text-orange-400">◔</span>{t("topstrip.deals")}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <CurrencyPicker />
          <LanguagePicker />
          <span className="mx-1 h-4 w-px bg-white/10" />
          <Link to="/disputes" className="hidden sm:inline hover:text-white px-2" data-testid="topstrip-help">{t("nav.help")}</Link>
          {!user ? (
            <>
              <Link to="/login" className="hover:text-white px-2" data-testid="topstrip-login">{t("nav.login")}</Link>
              <Link to="/register" className="hover:text-white px-2" data-testid="topstrip-register">{t("nav.register")}</Link>
            </>
          ) : (
            <>
              <Link to="/profile" className="hover:text-white px-2">Hi, {user.username}</Link>
              <button onClick={onLogout} className="hover:text-white px-2" data-testid="topstrip-logout">Logout</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const ThemeToggle = () => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] grid place-items-center transition-colors relative overflow-hidden dark:border-neutral-700 dark:hover:border-[#FF7A18]"
      data-testid="theme-toggle"
    >
      <Sun className={`h-5 w-5 text-neutral-700 absolute transition-all duration-300 ${isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"}`} />
      <Moon className={`h-5 w-5 text-[#FF7A18] absolute transition-all duration-300 ${isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"}`} />
    </button>
  );
};

const IconButton = ({ to, label, badge, children, testid }) => (
  <Link to={to}>
    <button aria-label={label} className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] dark:hover:border-[#FF7A18] grid place-items-center transition relative text-neutral-700 dark:text-neutral-200" data-testid={testid}>
      {children}
      {badge > 0 && (
        <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] font-semibold rounded-full h-4 min-w-4 px-1 grid place-items-center leading-none tabular-nums">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
  </Link>
);

const Header = () => {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");
  const [cartCount, setCartCount] = useState(0);
  const [notifCount, setNotifCount] = useState(0);
  const [recentNotifs, setRecentNotifs] = useState([]);
  const [categories, setCategories] = useState([]);
  const [compact, setCompact] = useState(false);
  const [cpOpen, setCpOpen] = useState(false);

  useCommandPaletteShortcut(setCpOpen);

  useEffect(() => {
    if (!user) { setCartCount(0); setNotifCount(0); setRecentNotifs([]); return; }
    api.get("/cart").then((r) => setCartCount(r.data.length)).catch(() => {});
    api.get("/notifications").then((r) => {
      const list = r.data || [];
      setNotifCount(list.filter((n) => !n.read).length);
      setRecentNotifs(list.slice(0, 4));
    }).catch(() => {});
  }, [user, location.pathname]);

  useEffect(() => { api.get("/categories").then((r) => setCategories(r.data)).catch(() => {}); }, []);

  // Compact-sticky on scroll (200px threshold with 40px hysteresis)
  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY || window.pageYOffset;
      setCompact((prev) => (prev ? y > 160 : y > 200));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="sticky top-0 z-40 bg-white dark:bg-neutral-950 transition-colors">
      <div className={`overflow-hidden transition-[max-height,opacity] duration-300 ${compact ? "max-h-0 opacity-0" : "max-h-16 opacity-100"}`}>
        <TopStrip user={user} onLogout={() => { logout(); navigate("/"); }} />
      </div>

      {/* Main bar */}
      <div className={`border-b border-neutral-200 dark:border-neutral-800 transition-shadow ${compact ? "shadow-sm" : ""}`}>
        <div className={`max-w-7xl mx-auto px-3 sm:px-4 flex items-center gap-2 sm:gap-3 transition-[height] duration-200 ${compact ? "h-14" : "h-16 sm:h-20"}`}>
          <GlobalNavMenu />

          <Link to="/" className="flex items-center gap-2 sm:gap-3 shrink-0" data-testid="brand-link">
            <BrandMark
              size={compact ? 32 : 44}
              data-testid="header-logo"
            />
            <div className={`hidden lg:block leading-tight transition-opacity ${compact ? "hidden xl:block" : ""}`}>
              <div className={`font-bold text-neutral-900 dark:text-neutral-100 ${compact ? "text-base" : "text-lg xl:text-xl"}`}>Mercari <span className="text-[#FF7A18]">Global</span></div>
              {!compact && <div className="text-[11px] text-neutral-500 dark:text-neutral-400 -mt-0.5">Smart Ecommerce</div>}
            </div>
          </Link>

          <div className="hidden md:block">
            <CategoryMegaMenu categories={categories} />
          </div>

          <SearchAutocomplete
            value={q}
            onChange={setQ}
            onSubmit={() => {}}
            placeholder={t("search.placeholder")}
            categories={categories}
          />

          <div className="hidden md:flex items-center gap-1.5 shrink-0">
            {!compact && <LiveSyncBadge />}

            <button
              type="button"
              onClick={() => setCpOpen(true)}
              className="hidden xl:inline-flex items-center gap-1.5 h-11 px-3 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] text-xs text-neutral-500 dark:text-neutral-400 transition"
              aria-label="Open command palette"
              data-testid="header-cp-btn"
              title="Command palette (⌘K)"
            >
              <Command className="h-3.5 w-3.5" />
              <span>⌘K</span>
            </button>

            <Link to="/marketplace">
              <button
                className={`rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white font-semibold text-sm shadow-sm hover:shadow-md transition-all flex items-center gap-1.5 ${compact ? "h-10 px-4" : "h-11 px-5"}`}
                data-testid="header-shopnow-btn"
              >
                <ShoppingBag className="h-4 w-4" /> Shop Now
              </button>
            </Link>

            <Link to={user ? "/sell" : "/login"}>
              <button
                className={`rounded-full bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110 text-white font-semibold text-sm shadow-sm hover:shadow-md transition-all flex items-center gap-1.5 ${compact ? "h-10 px-4" : "h-11 px-5"}`}
                data-testid="header-sell-btn"
              >
                <Package className="h-4 w-4" /> {t("nav.sell")}
              </button>
            </Link>

            <ThemeToggle />

            <IconButton to="/favorites" label="Favorites" testid="header-fav-btn">
              <Heart className="h-5 w-5" />
            </IconButton>

            <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition relative">
              <NotificationsBell />
              {notifCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center pointer-events-none">{notifCount}</span>
              )}
            </div>

            {user && (
              <IconButton to="/chat" label="Messages" testid="header-msg-btn">
                <MessageSquare className="h-5 w-5" />
              </IconButton>
            )}

            <MiniCart cartCount={cartCount} onCountChange={setCartCount} />

            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button aria-label="Account" className="relative h-10 w-10 sm:h-11 sm:w-11 rounded-full bg-gradient-to-br from-[#7DD3FC] to-[#2563EB] text-white grid place-items-center font-bold text-sm hover:brightness-110 transition overflow-hidden ring-2 ring-white/60 dark:ring-neutral-800" data-testid="header-user-btn">
                    {user.avatar ? (
                      <img
                        src={user.avatar}
                        alt={user.username}
                        className="h-full w-full object-cover"
                        referrerPolicy="no-referrer"
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                        data-testid="header-user-avatar-img"
                      />
                    ) : (
                      <span data-testid="header-user-initial">{user.username?.[0]?.toUpperCase() || "U"}</span>
                    )}
                    {notifCount > 0 && (
                      <span
                        className="absolute top-0 right-0 h-3 w-3 rounded-full bg-emerald-500 ring-2 ring-white dark:ring-neutral-950 shadow-[0_0_0_1px_rgba(0,0,0,0.05)] animate-pulse"
                        aria-label={`${notifCount} unread notifications`}
                        data-testid="header-user-unread-dot"
                      />
                    )}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-72">
                  <DropdownMenuLabel>Hi, {user.username}</DropdownMenuLabel>
                  {notifCount > 0 && (
                    <>
                      <DropdownMenuSeparator />
                      <div className="px-2 pt-1 pb-2" data-testid="avatar-notifs-preview">
                        <div className="flex items-center justify-between mb-1.5 px-1">
                          <span className="text-[11px] uppercase tracking-widest text-emerald-600 font-semibold">
                            {notifCount} unread
                          </span>
                          <button
                            onClick={async () => {
                              try { await api.post("/notifications/read-all"); setNotifCount(0); } catch { /* ignore */ }
                            }}
                            className="text-[11px] text-neutral-500 hover:text-[#2563EB] transition"
                            data-testid="avatar-notifs-markread"
                          >
                            Mark all read
                          </button>
                        </div>
                        <div className="space-y-1">
                          {recentNotifs.slice(0, 3).map((n) => (
                            <button
                              key={n.id}
                              onClick={() => { navigate(n.link || "/"); }}
                              className={`w-full text-left rounded-md px-2 py-1.5 transition ${n.read ? "hover:bg-neutral-100 dark:hover:bg-neutral-800" : "bg-blue-50 dark:bg-blue-950/30 hover:bg-blue-100 dark:hover:bg-blue-950/50"}`}
                              data-testid={`avatar-notif-${n.id}`}
                            >
                              <div className="text-xs font-medium line-clamp-1 dark:text-neutral-100">{n.title}</div>
                              {n.body && <div className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-1">{n.body}</div>}
                            </button>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/profile")}><User className="h-4 w-4 mr-2" /> {t("menu.profile")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/verify")}><ShieldCheck className="h-4 w-4 mr-2" /> Verification</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/wallet")}><Wallet className="h-4 w-4 mr-2" /> {t("menu.wallet")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/disputes")}><AlertCircle className="h-4 w-4 mr-2" /> {t("menu.disputes")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/referrals")}><Users className="h-4 w-4 mr-2" /> {t("menu.referrals")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/affiliate")}><LinkIcon className="h-4 w-4 mr-2" /> {t("menu.affiliate")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/my/store")}><Store className="h-4 w-4 mr-2" /> {t("menu.myStore")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/store/analytics")}><BarChart3 className="h-4 w-4 mr-2" /> {t("menu.storeAnalytics")}</DropdownMenuItem>
                  {user.role === "admin" && (
                    <DropdownMenuItem onClick={() => navigate("/admin")}><Settings className="h-4 w-4 mr-2" /> {t("menu.admin")}</DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => { logout(); navigate("/"); }}><LogOut className="h-4 w-4 mr-2" /> Logout</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link to="/login">
                <button className="h-11 px-4 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] dark:hover:border-[#FF7A18] text-sm font-semibold text-neutral-800 dark:text-neutral-100 transition flex items-center gap-1.5" data-testid="header-login-btn">
                  <User className="h-4 w-4" /> {t("nav.signIn")}
                </button>
              </Link>
            )}
          </div>

          <div className="md:hidden flex items-center gap-1 shrink-0">
            <ThemeToggle />
            <Link to="/cart" aria-label="Cart" className="h-10 w-10 rounded-full grid place-items-center relative text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition" data-testid="header-cart-btn-mobile">
              <ShoppingCart className="h-5 w-5" />
              {cartCount > 0 && (
                <span className="absolute top-0.5 right-0.5 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center">{cartCount}</span>
              )}
            </Link>
          </div>
        </div>
      </div>

      {/* Category ribbon (hidden when compact) */}
      <div className={`overflow-hidden transition-[max-height,opacity] duration-300 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950 ${compact ? "max-h-0 opacity-0 border-b-0" : "max-h-16 opacity-100"}`}>
        <div className="max-w-7xl mx-auto px-3 sm:px-4 py-2 sm:py-2.5 flex items-center gap-2 overflow-x-auto scrollbar-hide">
          <Link to="/search" data-testid="cat-pill-all">
            <button className="whitespace-nowrap px-4 sm:px-5 h-8 sm:h-9 rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white font-semibold text-xs sm:text-sm flex items-center gap-1.5 shrink-0 shadow-sm">
              <span className="text-base leading-none">▦</span> All Products
            </button>
          </Link>
          {categories.map((c) => (
            <Link key={c.id} to={`/search?category=${c.id}`} data-testid={`cat-pill-${c.slug}`}>
              <button className="whitespace-nowrap px-3 sm:px-4 h-8 sm:h-9 rounded-full bg-neutral-100 hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-200 font-medium text-xs sm:text-sm shrink-0 transition">
                {c.name}
              </button>
            </Link>
          ))}
        </div>
      </div>

      <CommandPalette open={cpOpen} onClose={() => setCpOpen(false)} />
    </header>
  );
};

export default Header;
